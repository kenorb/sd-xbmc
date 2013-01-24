# -*- coding: utf-8 -*-
import re, os, sys, StringIO, string
import struct
import urllib2
from threading import Thread
from binascii import unhexlify
import elementtree.ElementTree as ET
import xbmcaddon, xbmc, xbmcgui
import pLog

log = pLog.pLog()

scriptID = sys.modules[ "__main__" ].scriptID
scriptname = "Polish Live TV"
ptv = xbmcaddon.Addon(scriptID)

dbg = ptv.getSetting('default_debug')
#dstpath = ptv.getSetting('default_dstpath')
tmp = os.path.join( ptv.getAddonInfo('path'), "smth" )

class SMTH:
    def __init__(self):
        self.conta = ""
        self.failed = 0
        self.StreamIndex = 0
        self.VideoTS = tmp + os.sep + "video_ts"
        self.VideoChunk = tmp + os.sep + "video_chunk.ts"
        self.VideoTemp = tmp + os.sep + "video_temp.ts"
        self.AudioTS = tmp + os.sep + "audio_ts"
        self.AudioChunk = tmp + os.sep + "audio_chunk.raw"
        self.AudioRaw = tmp + os.sep + "audio_raw.raw"
        self.ASRate = ""
        
    def initialize(self, v_method, a_method, v_data, a_wave_format_ex, a_sample_rate):
        if a_wave_format_ex == 'None':
            a_wave_format_ex = 'no'
        if v_method == "WVC1":
            #self.VideoTS = path + os.sep + "video_ts.vc1"
            #VideoHdr = struct.pack("<H", v_data)
            VideoHdr = unhexlify(v_data)
            self.file_put_contents(self.VideoTS + ".vc1", VideoHdr)
        elif v_method == "AVC1" or v_method == "H264":
            #self.VideoTS = path + os.sep + "video_ts.264"
            #self.VideoTemp = path + os.sep + "video_temp.264"
            #self.VideoChunk = path + os.sep + "video_chunk.264"
            #VideoHdr = struct.pack(">H" , "000000016742801E965605017FCBFF820002002840000003004000000C98200016E3400044AA7F18E3040002DC680008954FE31C3B4244DC0000000168CA8D48")
            VideoHdr = unhexlify(v_data)
            self.file_put_contents(self.VideoTS + ".264", VideoHdr)
        if a_method == "WMA2":
            #self.AudioTS = path + os.sep + "audio_ts.wav"
            AudioHdr  = "\x52\x49\x46\x46" # 'RIFF'
            AudioHdr += "\x30\xFF\xFF\xFF" # chunk size
            AudioHdr += "\x57\x41\x56\x45\x66\x6D\x74\x20\x1C\x00\x00\x00" # 'WAVE' // 'fmt ' // sub chunk size
            #AudioHdr += struct.pack("<H", a_wave_format_ex)
            AudioHdr += unhexlify(a_wave_format_ex)
            AudioHdr += "\x64\x61\x74\x61"
            AudioHdr += "\x00\xFF\xFF\xFF"
            self.file_put_contents(self.AudioTS + ".wav", AudioHdr)
        elif a_method == "WMAPRO":
            #self.AudioTS = path + os.sep + "audio_ts.wav"
            AudioHdr  = "\x52\x49\x46\x46" #// 'RIFF'
            AudioHdr += "\x00\x00\x00\x00" #// chunk size
            AudioHdr += "\x57\x41\x56\x45\x66\x6D\x74\x20\x24\x00\x00\x00" #// 'WAVE' // 'fmt ' // sub chunk size = 40
            #AudioHdr += struct.pack("<H", a_wave_format_ex)
            AudioHdr += unhexlify(a_wave_format_ex)
            AudioHdr += "\x66\x61\x63\x74"  #// 'fact'
            AudioHdr += "\x04\x00\x00\x00" #// size of fact chunk
            AudioHdr += "\x00\x00\x00\x00" #// dwSampleLength
            AudioHdr += "\x64\x61\x74\x61\x30\xFF\xFF\xFF" #// 'data' // subchunk size        //Fake chunk size to prevent mplayer stopping! ;)
            self.file_put_contents(self.AudioTS + ".wav", AudioHdr)
        elif a_method == "AACL":
            #self.AudioTS = path + os.sep + "audio_ts.raw"
            self.ASRate = a_sample_rate
    
    def download_chunk(self, v_chunk, a_chunk, v_method, a_method):
        v_data = self.getResponseChunk(v_chunk)
        a_data = self.getResponseChunk(a_chunk)
        v_Upos = v_data.rfind("uuid")
        a_Upos = a_data.rfind("uuid")
        v_temp = v_data[v_Upos + 25:v_Upos + 33]
        a_temp = a_data[a_Upos + 25:a_Upos + 33]
        v_next = self.hexdec(self.bin2hex(v_temp))
        a_next = self.hexdec(self.bin2hex(a_temp))
        v_TsPos = v_data.rfind("mdat")
        a_TsPos = a_data.rfind("mdat")
        v_payload = v_data[v_TsPos + 4:]
        a_payload = a_data[a_TsPos + 4:]
        if v_method == "AVC1" or v_method == "H264":
            self.file_put_contents(self.VideoTemp, v_payload)
        self.file_put_contents(self.VideoTS + ".vc1", v_payload, True)
        self.file_put_contents(self.AudioTS + ".wav", a_payload, True)
            
    def file_put_contents(self, filename, data, append = False):
        if append:
            f = open(filename, "a")
        else:
            f = open(filename, "w")
        f.write(data)
        f.close()
    
    def calc_a_method(self, audio = {}):
        method = ""
        if audio['wave_format_ex'] != 'None':
            if audio['wave_format_ex'][0:4] == "6101":
                method = "WMA2"
            elif audio['wave_format_ex'][0:4] == "6201":
                method = "WMAPRO"
        return method
    
    def calc_wave_format_ex(self, audio = {}):
        wave_format_ex = ""
        if audio['audio_tag'] != 'None':
            attribs = [ audio['audio_tag'], audio['channels'], audio['sample_rate'], audio['packet_size'], audio['bits_per_sample'] ]
            wave_format_ex += self.str_split("%04s" % (hex(attribs[0])), 2)[::-1]
        return wave_format_ex
        
    def calc_tracks_delay(manifest, stream1_index, stream2_index):
        streams = manifest.findall('.//StreamIndex')
    
        s1 = streams[stream1_index]
        s2 = streams[stream2_index]
    
        s1_start_chunk = s1.find("c")
        s2_start_chunk = s2.find("c")
    
        s1_start_time = int(s1_start_chunk.attrib['t'])
        s2_start_time = int(s2_start_chunk.attrib['t'])
    
        s1_timescale = float(s1.attrib['TimeScale'])
        s2_timescale = float(s2.attrib['TimeScale'])
    
        # calc difference in seconds
        delay = s2_start_time / s2_timescale - \
                s1_start_time / s1_timescale
    
        return delay

    def str_split(s, n):
        """Split `s` into chunks `n` chars long."""
        ret = []
        for i in range(0, len(s), n):
            ret.append(s[i:i+n])
        return ret

    def getResponseChunk(self, url):
        response = urllib2.urlopen(url)
        return response.read()

    def bin2hex(self, bin):
        hx = bin.encode('hex')
        return hx

    def hexdec(self, hex):
        return int(hex, 16)

    def substr(s, start, length = None):
        """Returns the portion of string specified by the start and length 
        parameters.
        """
        if len(s) >= start:
            return False
        if not length:
            return s[start:]
        elif length > 0:
            return s[start:start + length]
        else:
            return s[start:length]
        

class Manifest:
    def __init__(self):
        #self.version = self.getVersion(manifest)
        #self.parser = ET.XMLParser(encoding="utf-8")
        pass
    
    def getVersion(self, manifest):
        if dbg == 'true':
            log.info('SMTH - getVersion() -> xml: ' + str(manifest))
        #parser = ET.XMLParser(encoding="utf-8")
        #elems = ET.parse(manifest, parser = parser).getroot()
        elems = ET.parse(manifest).getroot()
        return elems.attrib['MajorVersion']
    
    def getQualityLevel(self, manifest):
        video_quality = []
        audio_quality = []
        video_value = {}
        audio_value = {}
        version = self.getVersion(manifest)
        #parser = ET.XMLParser(encoding="utf-8")
        #elems = ET.parse(manifest, parser = parser).getroot()
        elems = ET.parse(manifest).getroot()
        streams = elems.findall('.//StreamIndex')
        for i,s in enumerate(streams):
            stream_type = s.attrib["Type"]
            if stream_type == 'video':
                url_name = s.attrib["Url"]
                chunks = s.attrib["Chunks"]
                qualities = s.findall("QualityLevel")
                for i,q in enumerate(qualities):
                    bitrate = q.attrib["Bitrate"]
                    fourcc = q.attrib["FourCC"]
                    codec_private_data = q.attrib["CodecPrivateData"]
                    width = "0"
                    height = "0"
                    if version == "1":
                        width = q.attrib["Width"]
                        height = q.attrib["Height"]
                    elif version == "2":
                        width = q.attrib["MaxWidth"]
                        height = q.attrib["MaxHeight"]
                    video_value = { 
                              'chunks': chunks,
                              'bitrate': bitrate,
                              'fourcc': fourcc,
                              'width': width,
                              'height': height,
                              'url_name': url_name,
                              'codec_private_data': codec_private_data
                            }
                    video_quality.append(video_value)
            elif stream_type == 'audio':
                url_name = s.attrib["Url"]
                chunks = s.attrib["Chunks"]
                lang = 'None'
                subtype = 'None'
                if version == "1":
                    lang = 'None'
                    subtype = s.attrib["Subtype"]
                elif version == "2":
                    lang = s.attrib["Language"]
                qualities = s.findall("QualityLevel")
                for i,q in enumerate(qualities):
                    bitrate = q.attrib["Bitrate"]
                    fourcc = 'None'
                    channels = 'None'
                    bits_per_sample = 'None'
                    sample_rate = 'None'
                    codec_private_data = 'None'
                    wave_format_ex = 'None'
                    packet_size = 'None'
                    audio_tag = 'None'
                    if version == "1":
                        wave_format_ex = q.attrib["WaveFormatEx"]
                    if version == "2":
                        fourcc = q.attrib["FourCC"]
                        channels = q.attrib["Channels"]
                        bits_per_sample = q.attrib["BitsPerSample"]
                        sample_rate = q.attrib["SamplingRate"]
                        codec_private_data = q.attrib["CodecPrivateData"]
                        packet_size = q.attrib["PacketSize"]
                        audio_tag = q.attrib["AudioTag"]
                    audio_value = {
                               'chunks': chunks,
                               'fourcc': fourcc,
                               'bitrate': bitrate,
                               'language': lang,
                               'subtype': subtype,
                               'url_name': url_name,
                               'channels': channels,
                               'bits_per_sample': bits_per_sample,
                               'sample_rate': sample_rate,
                               'codec_private_data': codec_private_data,
                               'wave_format_ex': wave_format_ex,
                               'packet_size': packet_size,
                               'audio_tag': audio_tag
                        }
                    audio_quality.append(audio_value)
        return { 'video': video_quality, 'audio': audio_quality }

    def getProtectionHeader(self, manifest):
        protect = {}
        elems = ET.parse(manifest).getroot()
        protection = elems.find('.//Protection')
        protect = {
                'systemId': protection.find('ProtectionHeader').attrib['SystemId'],
                'value': protection.find('ProtectionHeader').text
            }
        return protect

    def Timestamps(self, manifest):
        v_tab = []
        a_tab = []
        elems = ET.parse(manifest).getroot()
        streams = elems.findall('.//StreamIndex')
        for i,s in enumerate(streams):
            stream_type = s.attrib["Type"]
            if stream_type == "video":
                v_chunks = s.findall("c")
                for iv,v_c in enumerate(v_chunks):
                    v_tab.append(v_c.attrib["d"]) 
            elif stream_type == "audio":
                a_chunks = s.findall("c")
                for ia,a_c in enumerate(a_chunks):
                    a_tab.append(a_c.attrib["d"])
        return { 'v_timestamps': v_tab, 'a_timestamps': a_tab }

    def createChooseMenuTab(self, tab):
        out = []
        for i in range(len(tab)):
            #video: 1. H264, 1280x720 @ 2750000 bps
            #audio: 1. Polish - AACL 44100Hz 16bits 2ch @ 64000 bps
            a = i + 1
            item = str(a) + ". "
            try:
                if tab[i]['language'] != 'None':
                    item += tab[i]['language'].capitalize() + " - "
            except:
                pass
            try:
                if tab[i]['fourcc'] != 'None':
                    item += tab[i]['fourcc'] + ", "
            except:
                pass
            try:
                if tab[i]['subtype'] != 'None':
                    item += tab[i]['subtype'] + " "
            except:
                pass
            try:
                if tab[i]['width'] != 'None' and tab[i]['height'] != 'None':
                    item += tab[i]['width'] + "x" + tab[i]['height']
            except:
                pass
            try:
                if tab[i]['channels'] != 'None' and tab[i]['bits_per_sample'] != 'None' and tab[i]['sample_rate'] != 'None':
                    item += tab[i]['sample_rate'] + "Hz, " + tab[i]['bits_per_sample'] + "bits, " + tab[i]['channels'] + "ch"
            except:
                pass
            if tab[i]['bitrate'] != 'None':
                item += " @ " + tab[i]['bitrate'] + " bps"
            out.append(item)
        return out

    def getValueFromMenuTab(self, key, tab):
        value = {}
        for i in range(len(tab)):
            if key == i:
                value = tab[i]
                break
        return value
    
    
class DownloadAVChunks(Thread):
    def __init__(self, args = {}):
        Thread.__init__(self)
        self.a_timestamps = args['a_timestamps']
        self.v_timestamps = args['v_timestamps']
        self.base_url = args['base_url']
        self.a_bitrate = args['a_bitrate']
        self.v_bitrate = args['v_bitrate']
        self.a_url = args['a_url']
        self.v_url = args['v_url']
        self.a_method = args['a_method']
        self.v_method = args['v_method']
        self.smth = SMTH()
        
    def run(self):
        if dbg == "true":
            log.info('SMTH - DownloadAVChunks() -> v_timestamps: ' + str(self.v_timestamps))
            log.info('SMTH - DownloadAVChunks() -> v_timestamps[len]: ' + str(len(self.v_timestamps)))
            log.info('SMTH - DownloadAVChunks() -> a_timestamps: ' + str(self.a_timestamps))
            log.info('SMTH - DownloadAVChunks() -> a_timestamps[len]: ' + str(len(self.a_timestamps)))
        v_sum_time = 0
        a_sum_time = 0
        for i in range(len(self.v_timestamps)):
            v_sum_time = v_sum_time + int(self.v_timestamps[i])
            a_sum_time = a_sum_time + int(self.a_timestamps[i])
            v_chunk = self.base_url + self.v_url.replace("{bitrate}", self.v_bitrate).replace("{start time}", str(v_sum_time))
            a_chunk = self.base_url + self.a_url.replace("{bitrate}", self.a_bitrate).replace("{start time}", str(a_sum_time))
            if dbg == "true":
                log.info('SMTH - DownloadAVChunks() -> v_chunk[' + str(i) + ']: ' + v_chunk)
                log.info('SMTH - DownloadAVChunks() -> a_chunk[' + str(i) + ']: ' + a_chunk)
            self.smth.download_chunk(v_chunk, a_chunk, self.v_method, self.a_method)
            if i == 10:
                thumbnail = xbmc.getInfoImage("ListItem.Thumb")
                liz=xbmcgui.ListItem("bunny", iconImage="DefaultVideo.png", thumbnailImage=thumbnail)
                liz.setInfo( type="Video", infoLabels={ "Title": "bunny" } )
                xbmcPlayer = xbmc.Player()
                xbmcPlayer.play(tmp + os.sep + "video_ts.vc1", liz)
                
