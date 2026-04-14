# Program that reduces a score (.musicxml file) using pattern detection and note ranking.  
import os
import music21
from importlib import util
from collections import Counter
from collections import defaultdict

# Configuration for pattern reduction
PATTERN_LENGTH = 5
MIN_PATTERN_COUNT = 2

class SongConfiguration:
    def __init__(self, stream, limit):
        self.stream = stream
        self.limit = limit

    title = "Unknown Title"
    tempo = None
    time_signature = None
    dynamics = None

# This function sets up the environment, reads the input file, and extracts necessary information for processing.
def setup():
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
        stream = music21.converter.parse(file)
        #song = song.chordify()  # Chordify the song
        num_parts = len(stream.parts)
        print("File parsed and chordified successfully.")
        print(f"Found {num_parts} parts.\n")
    except Exception as e:
        print(f"Error parsing the file: {e}")
        exit()

    Song = SongConfiguration(stream, limit)

    # Extract tempo, time signature, dynamics, and song title
    tempo_indications = Song.stream.metronomeMarkBoundaries()
    Song.tempo = tempo_indications[0][2] if tempo_indications else None

    time_signature = Song.stream.recurse().getElementsByClass(music21.meter.TimeSignature)
    Song.time_signature = time_signature[0] if time_signature else None

    Song.dynamics = Song.stream.recurse().getElementsByClass(music21.dynamics.Dynamic)

    if Song.stream.metadata and Song.stream.metadata.title:
        Song.title = Song.stream.metadata.title

    # Generate file names for saving
    filename = file.split(".")
    title_pdf = filename[0] + ".pdf"
    title_xml = filename[0] + ".xml"

    # Remove existing files if they exist
    for output_file in [title_pdf, title_xml]:
        if os.path.exists(output_file):
            os.remove(output_file)
            print(f"Deleted existing file: {output_file}")
    
    return Song

def remove_lower_octaves(chord_obj, max_voices):
    # Convert the tuple of notes to a list so we can modify it
    notes = list(chord_obj.notes)
    
    # If the chord is already within the limit, skip processing
    if len(notes) <= max_voices:
        return notes

    # Group notes by pitch class (note name without the octave, e.g., 'C', 'G#')
    pitch_groups = {}
    for n in notes:
        if n.name not in pitch_groups:
            pitch_groups[n.name] = []
        pitch_groups[n.name].append(n)

    # Collect all the "removable" duplicate notes (the lower octaves)
    removable_notes = []
    for pc, group in pitch_groups.items():
        if len(group) > 1:
            # Sort the group from lowest pitch to highest pitch using their MIDI value
            group.sort(key=lambda x: x.pitch.midi)
            # Add all notes EXCEPT the highest one to our removable list
            removable_notes.extend(group[:-1])

    # Sort the removable notes from absolute lowest to highest
    # This ensures we delete a low bass octave before a mid-range octave
    removable_notes.sort(key=lambda x: x.pitch.midi)

    # Remove the lowest duplicates until we hit the voice limit
    for note_to_remove in removable_notes:
        if len(notes) > max_voices:
            notes.remove(note_to_remove)
        else:
            break

    return notes

# Function to reduce a chord to a specific number of voices
def reduce_chord(chord_obj, max_voices, repeated_patterns):
    filtered_notes = remove_lower_octaves(chord_obj, max_voices)

    # If the chord is too short (i.e., fewer notes than max_voices), only use the original notes
    return music21.chord.Chord(filtered_notes[:max_voices]) # Ensure the chord never exceeds max_voices

def add_notes(old_score, max_voices, chord_obj=music21.chord.Chord()):
    # Get the original notes from the chord
    original_notes = chord_obj.notes
    added_notes = list(original_notes)  # Start with the original notes
    old_score_chord = old_score.getElementsByOffset(chord_obj.offset)
    if len(old_score_chord) > 0 and old_score_chord[0].isChord:
        old_score_chord = old_score_chord[0] # Get the first element at that offset, which should be the chord in the original score

    # add notes from the original score back in until we hit the max voices limit
    if old_score_chord and old_score_chord.isChord:
        for note in old_score_chord.notes:
            if note not in added_notes:
                added_notes.append(note)
                if len(added_notes) >= max_voices:
                    break

    return music21.chord.Chord(added_notes)

# Function to reduce a music21 score to a specific number of voices (without adding extra notes)
def add_patterns(score_obj, repeated_patterns, chunk_size=PATTERN_LENGTH):
    reduced_stream = music21.stream.Part()

    # Preserve the time signature and tempo
    time_signature = score_obj.flatten().getElementsByClass(music21.meter.TimeSignature)
    tempo_mark = score_obj.flatten().getElementsByClass(music21.tempo.MetronomeMark)

    # Add time signature and tempo to the reduced stream if found
    if time_signature:
        reduced_stream.append(time_signature[0])  
    if tempo_mark:
        reduced_stream.append(tempo_mark[0])  

    # Loop through the original score
    notes_and_rests = score_obj.flatten().notesAndRests
    for i in range(len(notes_and_rests)-chunk_size+1): 
        element = notes_and_rests[i]
        noteList = get_chunk(notes_and_rests, i, chunk_size)
        pattern = get_chord_pattern(noteList)
        if pattern in repeated_patterns:
            print(f"Found repeated pattern at offset {element.offset}: {pattern} (occurs {repeated_patterns[pattern]} times)")
            #insert the pattern into the reduced stream
            for j in notes_and_rests[i:i+chunk_size]:
                #check for duplicates
                existing_element = reduced_stream.flatten().getElementsByOffset(j.offset)
                if len(existing_element) == 0:
                    reduced_stream.insert(j.offset, j)  # Insert the original note or chord at the correct offset. Might cause overlap issues.
        else:
            # if there's no pattern, just insert a rest as a placeholder to maintain timing
            # first check if there's already a note or rest at this offset in the reduced stream to avoid overwriting it
            existing_element = reduced_stream.flatten().getElementsByOffset(element.offset, mustBeginInSpan=False)
            existing_element = existing_element.notesAndRests # Filter to include only notes and rests. This seems to only be necessary at offset = 0 for some reason.
            if len(existing_element) == 0:
                rest = music21.note.Rest(quarterLength=element.quarterLength)
                reduced_stream.insert(element.offset, rest)

    # Loop through the last few elements that weren't included in the chunk processing and add rests to maintain timing
    for i in range(len(notes_and_rests)-chunk_size+1, len(notes_and_rests)):
        element = notes_and_rests[i]
        existing_element = reduced_stream.flatten().getElementsByOffset(element.offset, mustBeginInSpan=False)
        if len(existing_element) == 0:
            rest = music21.note.Rest(quarterLength=element.quarterLength)
            reduced_stream.insert(element.offset, rest)

    return reduced_stream

def reduce_score(score_obj, max_voices, repeated_patterns, reduced_stream):
    old_score = score_obj.flatten().notesAndRests
    # Loop through the old score and reduce or add notes to the new score as necessary
    for old_element in old_score.notesAndRests:
        element = reduced_stream.getElementsByOffset(old_element.offset)
        element = element.notesAndRests
        if len(element) == 0: # if there's no element at this offset in the new reduced stream, add the original element from the old score.
            reduced_stream.insert(old_element.offset, old_element)
            element = reduced_stream.getElementsByOffset(old_element.offset).notesAndRests
        element = element[0]
        offset = element.offset

        if element.isChord:
            if len(element.notes) > max_voices:
                reduced_chord = reduce_chord(element, max_voices, repeated_patterns) # reduce the chord to the max voices limit
            elif len(element.notes) < max_voices:
                reduced_chord = add_notes(old_score, max_voices, element) # add notes from the orignal score back in until we hit the max voices limit
            else:
                reduced_chord = element

            # Only append if the reduced chord has notes (no artificial additions)
            if reduced_chord.notes:
                reduced_stream.remove(element) # Remove the original chord
                reduced_stream.insertAndShift(offset, reduced_chord) # Insert the reduced chord at the same offset
        elif old_element.isChord:
            # check if there's a chord at this offset in the original score that we can add notes back from
            if len(old_element.notes) > max_voices:
                added_chord = reduce_chord(old_element, max_voices, repeated_patterns) # reduce the chord to the max voices limit
            else:
                added_chord = old_element
            reduced_stream.remove(element) # Remove the original element (likely a rest)
            reduced_stream.insert(offset, added_chord) # Insert the added chord at the same offset
        else:
            # both new and old elements are rests, so keep the rest from the old score
            reduced_stream.remove(element)
            reduced_stream.insert(offset, old_element)

    return reduced_stream

def get_chord_pattern(notes):
    distances = []
    noteLengths = []
    for i in range(len(notes)):
        if i < len(notes) - 1:
            distances.append(notes[i+1].pitch.midi - notes[i].pitch.midi)
        noteLengths.append(notes[i].duration.type)

    return tuple(distances), tuple(noteLengths) # convert to tuple for hashability

def get_chunk(notes, i, chunk_size=PATTERN_LENGTH):
    chunk = []
    for j in range(i, i+chunk_size):
        element = notes[j]
        if element.isNote:
            chunk.append(element)
        elif element.isChord:
            chunk.append(music21.note.Note(element.root(), duration=element.duration)) # only considering root for now, might expand to the whole chord or just use the highest note in the future
    return chunk

# Function to find repeated patterns of notes in the score
def find_repeated_patterns(score_obj, min_length=PATTERN_LENGTH):
    flat = score_obj.flatten().notesAndRests
    notesAndChords = [n for n in flat if n.isNote or n.isChord]
    
    for i in range(len(notesAndChords)-min_length+1):
        noteList = get_chunk(notesAndChords, i)
        repeated_patterns[get_chord_pattern(noteList)] += 1

# Main processing of chords
if __name__ == "__main__":
    Song = setup()
    repeated_patterns = defaultdict(int)
    for part in Song.stream.parts:
        part = part.chordify()
        find_repeated_patterns(part)
    # Filter out patterns that only occur once
    repeated_patterns = {pattern: count for pattern, count in repeated_patterns.items() if count >= MIN_PATTERN_COUNT}
    print(f"Identified {len(repeated_patterns)} sets of repeated patterns across the parts.")

    part_idx = 0
    new_score = music21.stream.Score(id='main_score')
    for part in Song.stream.parts:
        reduced_part = add_patterns(part, repeated_patterns)
        new_score.insert(0, reduced_part)  # Insert the reduced part directly into the score
        part_idx += 1
    new_score = new_score.chordify()  # Chordify the new score after adding patterns
    new_score = reduce_score(Song.stream.chordify(), Song.limit, repeated_patterns, new_score)

    # Apply dynamics to each part
    for dynamic in Song.dynamics:
        new_score.insert(dynamic.offset, dynamic)

    # Output new file
    output = new_score
    output.insert(0, music21.metadata.Metadata())
    output.metadata.title = f"{Song.title} - Reduced to {Song.limit} voices"
    output.write('musicxml.pdf', fp='MuTest')
    print("Done!")
