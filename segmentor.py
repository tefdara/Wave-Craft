#!/usr/bin/env python3.9
import os, sys
import librosa
import argparse
import soundfile as sf
from utils import bcolors, Utils
from onset_detector import OnsetDetector
from beat_detector import BeatDetector
import asyncio

utils = Utils()
class Segmentor:
    def __init__(self, args):
        self.args = args
        self.y, _ = librosa.load(self.args.input_file, sr=self.args.sample_rate)
        self.args.output_directory = self.args.output_directory or os.path.splitext(self.args.input_file)[0] + '_segments'
        self.metadata = utils.extract_metadata(self.args.input_file, self.args)
        self.base_segment_path = os.path.join(self.args.output_directory, os.path.basename(self.args.input_file).split('.')[0])
        
            
    def render_segments(self, y, segments):
        print(f'\n{bcolors.GREEN}Rendering segments...{bcolors.ENDC}\n')
        y_m, sr_m = sf.read(self.args.input_file)
        segments = librosa.frames_to_samples(segments, hop_length=self.args.hop_size, n_fft=self.args.n_fft)
        count = 0
        for i in range(len(segments) - 1):
            start_sample = segments[i]
            end_sample = segments[i + 1]
            segment = y_m[start_sample:end_sample]
            # skip segments that are too short
            segment_length = len(segment) / self.args.sample_rate
            if segment_length < self.args.min_length:
                print(f'{bcolors.YELLOW}Skipping segment {i+1} because it\'s too short{bcolors.ENDC} : {segment_length}s')
                continue
            count += 1
            faded_seg = utils.fade_io(audio=segment, sr=self.args.sample_rate, fade_duration=self.args.fade_duration, curve_type=self.args.curve_type)
            faded_seg = utils.filter(faded_seg, self.args.sample_rate, self.args.filter_frequency, btype=self.args.filter_type)
            normalised_seg = utils.normalise_audio(faded_seg, self.args.sample_rate, self.args.normalisation_level, self.args.normalisation_mode)
            segment_path = self.base_segment_path+f'_{count}.wav'
            print(f'{bcolors.CYAN}Saving segment {count} to {segment_path}.{bcolors.ENDC}')
            # Save segment to a new audio file
            sf.write(segment_path, normalised_seg, sr_m, format='WAV', subtype='PCM_24')
            utils.write_metadata(segment_path, self.metadata)

        utils.export_json(self.metadata, self.base_segment_path, data_type='seg_metadata')
                
        
        print(f'\n[{bcolors.GREEN}Done{bcolors.ENDC}]\n')


    def save_segments_as_txt(self, onsets):
        print(f'\n{bcolors.GREEN}Saving segments as text file...{bcolors.ENDC}')
        text_file_path = self.base_segment_path + '_segments.txt'
        with open (text_file_path, 'w') as file:
            for i in range(len(onsets) - 1):
                start_sample = onsets[i]
                end_sample = onsets[i + 1]
                # convert the sample indices to time in seconds
                # round the values to 6 decimal places but make sure there is at least 6 decimal places and add 0s if necessary
                start_time = round(librosa.samples_to_time(start_sample, sr=self.args.sample_rate), 6)
                start_time = f'{start_time:.6f}'
                end_time = round(librosa.samples_to_time(end_sample, sr=self.args.sample_rate), 6)
                end_time = f'{end_time:.6f}'
                # add a tab character between the start and end times
                file.write(f'{start_time}\t{end_time}\n')
        
        print(f'\n[{bcolors.GREEN}Done{bcolors.ENDC}]\n')
        
    def segment_using_txt(self, audio_path, txt_path, output_folder, file_format):
        
        y, sr = librosa.load(audio_path, sr=None)

        # Read the text file and split the audio based on the segments provided
        with open(txt_path, 'r') as file:
            lines = file.readlines()

            for i, line in enumerate(lines):
                tokens = line.split()
                start_time, end_time = tokens[:2]
                start_time = float(start_time) * 1000  
                end_time = float(end_time) * 1000 

                start_sample = int(start_time * sr / 1000)
                end_sample = int(end_time * sr / 1000)
                segment = y[start_sample:end_sample]

                # Adding fade-in and fade-out effects
                segment = utils.fade_io(segment, sr, fade_duration=self.args.fade_duration)
                segment_path = os.path.join(output_folder, f"segment_{i}.wav")
                sf.write(segment_path, segment, sr, format='WAV', subtype='FLOAT')
                
    def main(self):
        if self.args.segmentation_method == 'onset':
            detector = OnsetDetector(self.args)
            segments = asyncio.run(detector.main())
        elif self.args.segmentation_method == 'beat':
            detector = BeatDetector(self.args)
            segments = detector.main()
        
        user_input = input(f'Choose an action:\n1) Render segments\n2) Export segments as text file\n3) Exit\n')
        if user_input.lower() == '3':
            sys.exit()

        if self.args.segmentation_method == 'text':
            if(not self.args.input_text):
                self.args.input_text = os.path.splitext(self.args.input_file)[0] + '.txt'
            self.segment_using_txt(self.args.input_file, self.args.input_text, self.args.output_directory, self.args.file_format)
        else:
            os.makedirs(self.args.output_directory, exist_ok=True)
            if user_input.lower() == '1':
                self.render_segments(self.y, segments)
            elif user_input.lower() == '2':
                self.save_segments_as_txt(segments)


        if self.args.save_txt:
            self.save_segments_as_txt(segments, self.args.output_directory, self.args.sr)
            

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Split audio files based on segments from a text file.")
    parser.add_argument("-i", "--input-file", type=str, help="Path to the audio file (wav, aif, aiff).", required=True)
    parser.add_argument("-it", "--input-text", type=str, required=False,
                        help="The text file containing the segmentation data. Defaults to the nameofaudio.txt")
    parser.add_argument("-o", "--output-directory", type=str, default=None, help="Path to the output directory. Optional.", required=False)
    parser.add_argument("-m", "--segmentation-method", type=str, choices=["onset", "beat", "text"], required=False, default="onset",
                        help="Segmentation method to use.")
    parser.add_argument("-st", "--save-txt", action='store_true', help="Save segment times to a text file.")
    parser.add_argument("-ml", "--min-length", type=float, default=0.1, help="Minimum length of a segment in seconds. Default is 0.1s.\
                        anything shorter won't be used", required=False)
    parser.add_argument("-f", "--fade-duration", type=int, default=20, help="Duration in ms for fade in and out. Default is 50ms.", required=False)
    parser.add_argument("-c", "--curve-type", type=str, choices=['exp', 'log', 'linear', 's_curve','hann'], default="exp",\
                        help="Type of curve to use for fade in and out. Default is exponential.", required=False)
    parser.add_argument("-ff", "--filter-frequency", type=int, default=40, 
                        help="Frequency to use for the high-pass filter. Default is 40 Hz. Set to 0 to disable", required=False)
    parser.add_argument("-ft", "--filter-type", type=str, choices=['high', 'low'], default="high", 
                        help="Type of filter to use. Default is high-pass.", required=False)
    parser.add_argument("-nl", "--normalisation-level", type=float, default=-3, required=False,
                        help="Normalisation level, default is -3 db.")
    parser.add_argument("-nm", "--normalisation-mode", type=str, default="peak", choices=["peak", "rms", "loudness"], 
                        help="Normalisation mode; default is RMS.", required=False)
    parser.add_argument("-hpss", "--source-separation", type=str, default=None, choices=["harmonic", "percussive"], required=False,
                        help="Decompose the signal into harmonic and percussive components, before computing segments.")
    parser.add_argument("-k", type=int, default=5, help="Number of beat clusters to detect. Default is 5.", required=False)
    parser.add_argument("--sample-rate", type=int, default=48000, help="Sample rate of the audio file. Default is 48000.", required=False)
    parser.add_argument("--fmin", type=float, default=20, help="Minimum frequency. Default is 27.5.", required=False)
    parser.add_argument("--fmax", type=float, default=16000, help="Maximum frequency. Default is 16000", required=False)
    parser.add_argument("-t", "--onset-threshold", type=float, default=0.1, help="Onset detection threshold. Default is 0.1.", required=False)
    parser.add_argument("--n-fft", type=int, default=2048, help="FFT size. Default is 2048.", required=False)
    parser.add_argument("--hop-size", type=int, default=512, help="Hop size. Default is 512.", required=False)

    # text segmentation parameters
    # parser.add_argument("--segment-times", type=str, default=None, help="Segment times in seconds separated by commas. Optional.", required=False)

    args = parser.parse_args()
    segmentor = Segmentor(args)
    segmentor.main()
    
    