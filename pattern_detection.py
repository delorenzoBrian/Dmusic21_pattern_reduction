#This code reduces a score based on pattern reduction only. 
import os
import music21
from importlib import util
from collections import Counter

# Verify that music21 is installed
print("Checking if 'music21' is installed...")
if util.find_spec("music21") is not None:
    print("'music21' is installed and ready to use.")
else:
    print("Error: 'music21' is not installed.")
    exit()

# Set up MuseScore paths
music21.environment.set('musicxmlPath', r'C:/Program Files/MuseScore 4/bin/Musescore4.exe')
music21.environment.set('musescoreDirectPNGPath', r'C:/Program Files/MuseScore 4/bin/Musescore4.exe')

# Read the input music xml file and get the user's desired number of parts
file = input("Please enter a filename:\n")
print(f"You entered {file}")
limit = int(input("Enter the maximum number of notes played simultaneously.\n"))
print(f"{limit} voices of polyphony will be preserved.")
print("Running converter...\n")

# Parse the file using music21
try:
    song = music21.converter.parse(file)
    song = song.chordify()  # Chordify the song
    print("File parsed and chordified successfully.")
except Exception as e:
    print(f"Error parsing the file: {e}")
    exit()

# Extract tempo, time signature, and dynamics
tempo_indications = song.metronomeMarkBoundaries()
original_tempo = tempo_indications[0][2] if tempo_indications else None

time_signature = song.recurse().getElementsByClass(music21.meter.TimeSignature)
original_time_signature = time_signature[0] if time_signature else None

dynamics = song.recurse().getElementsByClass(music21.dynamics.Dynamic)

# Generate file names for saving
filename = file.split(".")
title_pdf = filename[0] + ".pdf"
title_xml = filename[0] + ".xml"

# Remove existing files if they exist
for output_file in [title_pdf, title_xml, 'dropped_notes.pdf', 'dropped_notes.musicxml']:
    if os.path.exists(output_file):
        os.remove(output_file)
        print(f"Deleted existing file: {output_file}")

# Save the original results as PDF and XML
try:
    print("Attempting to write original score as MusicXML and PDF...")
    song.write('musicxml', fp='MuTrans.xml')
    song.write('musicxml.pdf', fp='MuTrans.pdf')
    print("MusicXML and PDF written successfully.")
except Exception as e:
    print(f"Error writing files: {e}")
    exit()

# Rename files if they exist
if os.path.exists('MuTrans.xml'):
    os.rename('MuTrans.xml', title_xml)
    print(f"Renamed MuTrans.xml to {title_xml}")
else:
    print("Error: 'MuTrans.xml' was not created.")

if os.path.exists('MuTrans.pdf'):
    os.rename('MuTrans.pdf', title_pdf)
    print(f"Renamed MuTrans.pdf to {title_pdf}")
else:
    print("Error: 'MuTrans.pdf' was not created.")

print("Done saving original score as PDF and XML.")

# Function to find repeated patterns of notes in the score
def find_repeated_patterns(score_obj, min_length=5):
    patterns = []
    
    # Flatten the score to analyze notes
    notes = [n for n in score_obj.flatten().notes if n.isNote]
    
    for i in range(len(notes)):
        for j in range(i + min_length, len(notes) + 1):
            pattern = tuple(n.nameWithOctave for n in notes[i:j])  # Create a tuple of note names
            patterns.append(pattern)

    # Count occurrences of each pattern
    pattern_counts = Counter(patterns)
    
    # Filter patterns to include only those that occur more than once
    repeated_patterns = {p: count for p, count in pattern_counts.items() if count > 1}
    
    return repeated_patterns

# Function to prioritize melody notes in the reduced notes based on the found repeated patterns
def prioritize_melody(reduced_notes, repeated_patterns):
    priority_notes = set()
    for pattern in repeated_patterns:
        priority_notes.update(pattern)  # Add all notes in the pattern to the priority set
    
    # Keep notes from the reduced chord based on priority
    prioritized_notes = [n for n in reduced_notes if n.nameWithOctave in priority_notes]
    
    # If there are not enough priority notes, fill with remaining notes
    remaining_notes = [note for note in reduced_notes if note not in prioritized_notes]
    while len(prioritized_notes) < limit and remaining_notes:
        prioritized_notes.append(remaining_notes.pop(0))
    
    return prioritized_notes

# Function to reduce the number of notes in a chord according to voice leading principles
def reduce_chord(chord_obj, max_voices, repeated_patterns):
    notes = chord_obj.notes
    reduced_notes = []

    # Prioritize melody notes first
    prioritized_notes = prioritize_melody(notes, repeated_patterns)
    
    # Limit the number of notes based on max_voices
    reduced_notes = prioritized_notes[:max_voices]
    
    return music21.chord.Chord(reduced_notes)

# Function to reduce a music21 score to a specific number of voices
def reduce_score(score_obj, max_voices, repeated_patterns):
    reduced_stream = music21.stream.Part()

    # Preserve the time signature and tempo
    time_signature = score_obj.flat.getElementsByClass(music21.meter.TimeSignature)
    tempo_mark = score_obj.flat.getElementsByClass(music21.tempo.MetronomeMark)

    # Add time signature and tempo to the reduced stream if found
    if time_signature:
        reduced_stream.append(time_signature[0])  
    if tempo_mark:
        reduced_stream.append(tempo_mark[0])  

    # Loop through the original score
    for element in score_obj.flatten().notesAndRests:
        if isinstance(element, music21.chord.Chord):
            reduced_chord = reduce_chord(element, max_voices, repeated_patterns)
            # Only append if the reduced chord has notes
            if reduced_chord.notes:
                reduced_stream.append(reduced_chord)
        else:
            reduced_stream.append(element)  # Append rests or other elements

    return reduced_stream

# Main processing of chords
repeated_patterns = find_repeated_patterns(song)

if limit <= 1:
    part = music21.stream.Part()
    new_score = music21.stream.Score(id='main_score')
    new_score.insert(0, part)

    # Add tempo and time signature if available
    if original_tempo:
        part.append(original_tempo)
    if original_time_signature:
        part.append(original_time_signature)

    for thisChord in song.recurse().getElementsByClass(['Chord', 'Rest']):
        if thisChord.isChord:
            reduced_chord = reduce_chord(thisChord, limit, repeated_patterns)
            if reduced_chord.notes:
                part.append(reduced_chord)
        else:
            part.append(thisChord)  # Append rests or other elements
else:
    reduced_score = reduce_score(song, limit, repeated_patterns)
    new_score = music21.stream.Score(id='main_score')
    new_score.append(reduced_score)  # Append the reduced score directly

# Apply dynamics to each part
for dynamic in dynamics:
    new_score.insert(dynamic.offset, dynamic)

# Output new file
output = new_score.chordify()
output.write('musicxml', fp=f"{filename[0]}_reduced.musicxml")
output.write('musicxml.pdf', fp=f"{filename[0]}_reduced.pdf")
print("Reduced score saved as dropped_notes.musicxml and dropped_notes.pdf")

print("Processing complete.")