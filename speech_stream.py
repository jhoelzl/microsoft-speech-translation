"""
Python sample demonstrating use of Microsoft Translator Speech Translation API.
"""

import os

try:
    from StringIO import StringIO
except ImportError:
    import io as StringIO

import struct

try:
    import thread
except ImportError:
    import _thread as thread


import time
import uuid
import wave
import sys
import pyaudio
import threading
import websocket

import json
import requests
import subprocess

def get_wave_header(frame_rate):
    """
    Generate WAV header that precedes actual audio data sent to the speech translation service.

    :param frame_rate: Sampling frequency (8000 for 8kHz or 16000 for 16kHz).
    :return: binary string
    """

    if frame_rate not in [8000, 16000]:
        raise ValueError("Sampling frequency, frame_rate, should be 8000 or 16000.")

    nchannels = 1
    bytes_per_sample = 2

    output = StringIO.BytesIO()
    output.write(b'RIFF')
    output.write(struct.pack('<L', 0))
    output.write(b'WAVE')
    output.write(b'fmt ')
    output.write(struct.pack('<L', 18))
    output.write(struct.pack('<H', 0x0001))
    output.write(struct.pack('<H', nchannels))
    output.write(struct.pack('<L', frame_rate))
    output.write(struct.pack('<L', frame_rate * nchannels * bytes_per_sample))
    output.write(struct.pack('<H', nchannels * bytes_per_sample))
    output.write(struct.pack('<H', bytes_per_sample * 8))
    output.write(struct.pack('<H', 0))
    output.write(b'data')
    output.write(struct.pack('<L', 0))

    data = output.getvalue()

    output.close()

    return data

if __name__ == "__main__":

    # Get Token
    headers = {'Ocp-Apim-Subscription-Key': 'xxx'}
    payload = {}
    r = requests.post("https://api.cognitive.microsoft.com/sts/v1.0/issueToken", data="", headers=headers)
    token = r.content
    
    #payload = json.load(open("request.json"))
    #headers = {'content-type': 'application/json', 'Accept-Charset': 'UTF-8'}
    #r = requests.post(url, data=json.dumps(payload), headers=headers)
    CHUNK = 1024
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 16000
    
    p = pyaudio.PyAudio()
    
    stream = p.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=CHUNK)

    translate_from = 'en'
    translate_to = 'de'
    features = "Partial,TextToSpeech,TimingInfo"

    # Transcription results will be saved into a new folder in the current directory
    output_folder = os.path.join(os.getcwd(), uuid.uuid4().hex)

    # These variables keep track of the number of text-to-speech segments received.
    # Each segment will be saved in its own audio file in the output folder.
    tts_state = {'count': 0}

    # Setup functions for the Websocket connection

    def on_open(ws):
        """
        Callback executed once the Websocket connection is opened.
        This function handles streaming of audio to the server.

        :param ws: Websocket client.
        """

        print('Connected. Server generated request ID = ', ws.sock.headers['x-requestid'])

        def run(*args):
            """Background task which streams audio."""
            # Send WAVE header to provide audio format information
            data = get_wave_header(16000)
            ws.send(data, websocket.ABNF.OPCODE_BINARY)
            # Stream pyAudio Microphone Audio
            while True:
                #sys.stdout.write('.')
                data = stream.read(CHUNK)
                ws.send(data, websocket.ABNF.OPCODE_BINARY)

            stream.stop_stream()
            stream.close()
            p.terminate()
            ws.close()
            print('Background thread terminating...')

        thread.start_new_thread(run, ())

    def on_close(ws):
        """
        Callback executed once the Websocket connection is closed.

        :param ws: Websocket client.
        """
        print('Connection closed...')

        
    def on_error(ws, error):
        """
        Callback executed when an issue occurs during the connection.

        :param ws: Websocket client.
        """
        print(error)

    def on_data(ws, message, message_type, fin):
        """
        Callback executed when Websocket messages are received from the server.

        :param ws: Websocket client.
        :param message: Message data as utf-8 string.
        :param message_type: Message type: ABNF.OPCODE_TEXT or ABNF.OPCODE_BINARY.
        :param fin: Websocket FIN bit. If 0, the data continues.
        """

        if message_type == websocket.ABNF.OPCODE_TEXT:
            print('\n', message, '\n')
        else:
            tts_count = tts_state['count']
            tts_file = tts_state.get('file', None)
            if tts_file is None:
                tts_count += 1
                tts_state['count'] = tts_count
                fname = "tts_{0}.mp3".format(tts_count)
                print("\nTTS segment #{0} begins (file name: '{1}').\n".format(tts_count, fname))
                if not os.path.exists(output_folder):
                    os.makedirs(output_folder)
                tts_file = open(os.path.join(output_folder, fname), 'wb')
                tts_state['file'] = tts_file
            tts_file.write(message)
            if fin:
                print('\n', "TTS segment #{0} ends.'.".format(tts_count), '\n')
                tts_file.close()
                del tts_state['file']
                # Play TTS
                os.system('mpg123 ' + output_folder + "/" + fname)

    client_trace_id = str(uuid.uuid4())
    request_url = "wss://dev.microsofttranslator.com/speech/translate?from={0}&to={1}&features={2}&format={3}&ProfanityAction={4}&ProfanityMarker={5}&api-version=1.0".format(translate_from, translate_to, features,'audio/mp3','Marked','Tag')

    print("Ready to connect...")
    print("Request URL      = {0})".format(request_url))
    print("ClientTraceId    = {0}".format(client_trace_id))
    print('Results location = %s\n' % output_folder)

    ws_client = websocket.WebSocketApp(
        request_url,
        header=[
            'Authorization: Bearer ' + token.decode('utf-8'),
            'X-ClientTraceId: ' + client_trace_id
        ],
        on_open=on_open,
        on_data=on_data,
        on_error=on_error,
        on_close=on_close
    )
    ws_client.run_forever()

