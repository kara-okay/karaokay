#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import os
os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
import sys, random, math, re, pygame, numpy, argparse
from os.path import abspath, realpath, isfile
from moviepy.editor import *

class ParserError(Exception):
  pass
  
class KaraOkay:
  def __init__(self, filename, outfile, audiofile, fontfile, force, debug, suppress_plug):
    self.filename = filename
    self.outfile = outfile
    self.audiofile = audiofile
    self.fontfile = fontfile
    self.force_arg = force
    self.debug = debug
    self.suppress_plug = suppress_plug

    self.width, self.height = 1280, 720
    self.bgcolor = 0, 0, 50
    self.fontcolor = 240, 240, 240
    self.peekcolor = 150, 150, 150
    self.hicolor = 90, 255, 90
    self.fps = 30
    
    # Seconds: 1, 10, 1.1, 10.99, Minutes: 1:00, 1:01.0
    self.tsRegex = '(?:(\d+):)?(\d?\d(?:\.\d\d?)?)'
    self.secondsRegex = '(\d?\d(?:\.\d\d?)?)'
    
    # Pre start gap. If possible, show the card this many seconds before
    # starting.
    self.show_before = 1.5
    
    # Duration of the cue
    self.cue_length = 1
        
    # If the next card starts sooner than the 
    # threshold, we provide a peek line. Given in seconds.
    self.peek_threshold = 1
    
    # If the gap between cards if bigger than the threshold, we show
    # a pause bar
    self.pause_threshold = 3
    # Time between the end of a pause and the next card
    # (should be identical to self.show_before)
    self.pause_gap = self.show_before

    self.slotpositions = []
  
    self.data = {
      "timestamps": [],
      "cards": [],
      "pre_gaps": [],
      "post_gaps": [],
      "duration": 0,
      "lines": []
    }

    self.maxLineLength = self.width * .8

    self.referenceFontSize = self.fontSize = 100

    if self.fontfile and isfile(abspath(realpath(self.fontfile))):
      self.fontfile = abspath(realpath(self.fontfile))
    else:
      self.fontfile = "./fonts/SourceSansPro-Semibold.ttf"

    self.updateFont()
    
  def run(self):
    """
      Parse the file, layout and render the movie.
    """
    filename = abspath(realpath(self.filename))
    if not isfile(filename):
      sys.exit(self.filename + ": No such file or directory.")
    try:
      self.parse(self.filename)
    except ParserError as e:
      sys.exit("Parser error. Not a valid kok file. Error occurred in line: " + str(e))

    outfile = filename + ".mp4"
    outfile = outfile.replace(".kok", "")
    if not self.outfile == None:
      outfile = self.outfile
    if isfile(outfile) and not self.force_arg:
      sys.exit("File" + outfile + " already exists. Please remove, use --force or specify a different file using -o.")

    audioclip = None
    if self.audiofile:
      audiofile = abspath(realpath(self.audiofile))
      if not isfile(audiofile):
        sys.exit(self.audiofile + ": No such file or directory.")
      audioclip = AudioFileClip(audiofile)

    pygame.init()
    self.screen = pygame.display.set_mode((self.width, self.height))

    self.layout()
    if self.debug:
      self.debug_output()

    clip = VideoClip(self.render, duration = self.data["duration"])
    if audioclip:
      clip = clip.set_audio(audioclip)
    clip.write_videofile(outfile, fps=self.fps)
  
  def render(self, t):
    """
      Producer for moviepy.editor.Videoclip. t is time in seconds
    """
    self.drawBackground()
    if self.debug:
      text = self.font.render(str(int(t*100)/100), True, self.fontcolor)
      self.screen.blit(text, text.get_rect())
    
    displaylines = []
    last_hide = 0
    for line in self.data["lines"]:
      if line["hide"] > last_hide:
        last_hide = line["hide"]
      if line["show"] > t or line["hide"] <= t:
        continue
      displaylines.append(line)

    if not self.suppress_plug and t > last_hide:
      self.show_plug()

    if len(displaylines) == 0: 
      pygame.display.flip()
      return numpy.flip(numpy.rot90(pygame.surfarray.array3d(self.screen)), 0)

    for line in displaylines:
      if line["display"] == "pause":
        rect = pygame.Rect(0, 0, self.maxLineLength , self.lineheight)
        rect.midtop = self.width/2, self.slotpositions[line["slot"]]
        pygame.draw.rect(self.screen, self.fontcolor, rect)
        
        percentage = (t - line["show"])/(line["hide"] - line["show"])
        w = self.maxLineLength  * percentage
        rect2 = pygame.Rect(0, 0, w , self.lineheight)
        rect2.topleft = rect.topleft
        pygame.draw.rect(self.screen, self.hicolor, rect2)
        continue
              
      textcolor = self.fontcolor
      if line["display"] == "peek":
        textcolor = self.peekcolor
      text = self.font.render(line["text"], True, textcolor)
      textrect = text.get_rect()
      textrect.centerx = self.width/2
      textrect.top = self.slotpositions[line["slot"]]
      self.screen.blit(text, textrect)
      if line["display"] == "peek":
        # peek lines will never be highlighted
        continue
      
      # Highlighting
      if line["parts"] == False:
        percentage = 0
        if t > line["start"]:
          percentage = (t - line["start"])/(line["end"] - line["start"] - 1/self.fps)
        if percentage > 1:
          percentage = 1
        cliptext = self.font.render(line["text"], True, self.hicolor)
        cliprect =  pygame.Rect(0, 0, textrect.w * percentage, textrect.h)
        cliptext = cliptext.subsurface(cliprect)
        self.screen.blit(cliptext, textrect)
      else:
        lastoffset = 0
        for part in line["parts"]:
          percentage = 0
          if t > line["start"]:
            percentage = (t - part["start"])/(part["end"] - part["start"] - 1/self.fps)
          if percentage <= 0:
            continue
          if percentage > 1:
            percentage = 1

          cliptext = self.font.render(part["text"], True, self.hicolor)
          cliprect = cliptext.get_rect()
          cliprect =  pygame.Rect(0, 0, cliprect.w * percentage, cliprect.h)
          cliptext = cliptext.subsurface(cliprect)

          cliprect.left = textrect.left + lastoffset
          cliprect.top = textrect.top
          lastoffset += cliprect.w

          self.screen.blit(cliptext, cliprect)

      if line["display"] == "cue":
        percentage = 1
        if t > line["start"] - self.cue_length:
          percentage = (line["start"] - t)/self.cue_length
        if t > line["start"]:
          continue
        rect = pygame.Rect(0, 0, self.lineheight * percentage , self.lineheight)
        rect.topright = textrect.topleft
        pygame.draw.rect(self.screen, self.fontcolor, rect)

    pygame.display.flip()
    
    return numpy.flip(numpy.rot90(pygame.surfarray.array3d(self.screen)), 0)

  def layout(self):
    """
      Layout the movie. Determine what to show where and when.
    """
    #Let's count lines we use, to see how many we need in the end.
    maxslots = 0

    # Determine the length of the pre and post gaps of every card
    cursor = 0
    for card_idx in range(len(self.data["cards"])):
      timestamps = self.data["timestamps"][card_idx]
      start = timestamps[0]
      end = timestamps[1]
      self.data["pre_gaps"].append(start - cursor)
      cursor = end
    # Post = pre[1:] and the last element set to "infinity"
    self.data["post_gaps"] = self.data["pre_gaps"][1:]
    self.data["post_gaps"].append(self.data["duration"] - end)

    layout = []
    # Step 1: Figure out card display times, peeks, cues and pauses
    lastEnd = 0;
    for card_idx in range(len(self.data["cards"])):
      card = self.data["cards"][card_idx]
      timestamps = self.data["timestamps"][card_idx]
      start = timestamps[0]
      end = timestamps[1]
      show = start
      hide = end
      pre_gap =  self.data["pre_gaps"][card_idx]
      post_gap =  self.data["post_gaps"][card_idx]
      
      # If we have a long gap before this card, fit in a pause.
      # Adjust the "show" value accordingly.
      if pre_gap > self.pause_threshold:
        layout.append({
          "display": "pause",
          "show": lastEnd,
          "hide": start - self.pause_gap
        })
        show = start - self.pause_gap
      lastEnd = end
      
      # Determine when to show the card, whether to cue it and
      # if there will be a peek to the next card.
      if pre_gap > self.show_before:
        show = start - self.show_before
      else: 
        show = start - pre_gap
      
      display_type = "regular"
      if self.data["pre_gaps"][card_idx] > self.cue_length:
        display_type = "cue"
        
      peek = False
      slots = len(card)
      if post_gap < self.peek_threshold:
        peek = True
        slots += 1
      
      if slots > maxslots:
        maxslots = slots

      layout.append({ 
        "display": display_type,
        "card": card_idx,
        "show": show,
        "hide": hide,
        "peek": peek
      })      

    
    # Step 2: Break the layout down to lines, assign them to slots
    # and figure out the timings of each lines.
    # Moved to its own method, this one is too long anyway ...
    self.layoutlines(layout, maxslots); 

    # Determine optimal font size
    # Step 3: Line length
    longest = pygame.Rect(0,0,0,0)
    for l in self.data["lines"]:
      if l["display"] == "peek" or l["display"] == "pause": continue
      renderedLine = self.font.render(l["text"], True, self.fontcolor)
      renderedLineRect = renderedLine.get_rect()
      if renderedLineRect.w > longest.w:
        longest = renderedLineRect
    self.fontSize = int(self.referenceFontSize * self.maxLineLength/longest.w)
    # This will save the actual lineheight in px to self.lineheight
    self.updateFont()
    
    # Step 4: Number of lines
    # We assume a blank half an line on bottom and top, and half line
    # between each slot, so maxslots + 1 + (maxslots -1)/2 lines.
    # Which is 1.5 * maxslots - 0.5
    # If that's heigher than our screen, adjust lineheight accordingly
    slotsheight = self.lineheight * 1.5 * maxslots - 0.5
    if slotsheight > self.height:
      self.fontSize = int(self.fontSize * self.height/slotsheight)
      self.updateFont()    
    
    # Step 5: Slot positions 
    # Calculate the positions of the slots, now that we know how many
    # lines we need.
    top = (self.height - (self.lineheight * 1.5 * maxslots - 0.5))/2
    for i in range(maxslots):
      self.slotpositions.append(top)
      top += 1.5 * self.lineheight

  def layoutlines(self, layout, maxslots):
    """
      Figure out the timings for the lines in card, which may be tricky
      because of "intra" timings, which are timestamps withing a line.
    """
    for item in layout:
      if "pause" == item["display"]:
        item["slot"] = int((maxslots-1)/2)
        self.data["lines"].append(item) 
        continue
          
      card = self.data["cards"][item["card"]]
      timestamps = self.data["timestamps"][item["card"]]
      start = timestamps[0]
      end = timestamps[1]
      
      # Collect all possible timestamps, which are start of line, end
      # of line and all timestamps within a line.
      # Not all of them may be defined, so we just note down a "?" and
      # fix it up later.
      timestamps = []
      for line_idx in range(len(card)):
        line = card[line_idx]
        
        start_match = re.match("\[(.*?)\]", line)
        ts = "?"
        if start_match:
          ts = float(start_match.group(1))
        timestamps.append(["start", ts, line_idx])
        
        intra_search = re.finditer(".\[(.*?)\].", line)
        for intra_match in intra_search:
          ts = float(intra_match.group(1))
          timestamps.append(["intra", ts, line_idx])

        end_match = re.match(".*\[" + self.secondsRegex + "\]$", line)
        ts = "?"
        if end_match:
          ts = float(end_match.group(1))
        timestamps.append(["end", ts, line_idx])

      # Fix-up start and end of the card
      if timestamps[0][1] == "?":
        timestamps[0][1] = start
      if timestamps[len(timestamps) - 1][1] == "?":
        timestamps[len(timestamps) - 1][1] = end
      
      # Fix-up the remaining line starts and end as much as we can.
      # We're may remove elements here, so we go backward to avoid 
      # messing up our idices.
      for idx in range(len(timestamps) - 2, 0, -1):
        # We know the line start after an unknown line end
        if (timestamps[idx][0] == "start" 
              and not timestamps[idx][1] == "?"
              and timestamps[idx - 1][0] == "end" 
              and timestamps[idx - 1][1] == "?"):
          timestamps[idx - 1][1] = timestamps[idx][1]
          
        # We know the line end before an unknown line start
        if (timestamps[idx][0] == "start" 
              and timestamps[idx][1] == "?"
              and timestamps[idx - 1][0] == "end" 
              and not timestamps[idx - 1][1] == "?"):
          timestamps[idx][1] = timestamps[idx - 1][1]    
           
        # If we have unknown end and start, it acts as a single
        # timstamp
        if (timestamps[idx][0] == "start" 
              and timestamps[idx][1] == "?"
              and timestamps[idx - 1][0] == "end" 
              and timestamps[idx - 1][1] == "?"):
          timestamps[idx - 1][0] = "endstart"     
          del timestamps[idx]
      
      # Now calculate the missing time stamps, by simply dividing the
      # timespan between the known timestamps
      questionmarkcounter = 0
      for idx in range(1, len(timestamps)):
        if timestamps[idx][1] == "?":
          questionmarkcounter += 1
        else:
          if questionmarkcounter == 0:
            continue
          known_start_idx = idx - questionmarkcounter - 1
          known_start = timestamps[known_start_idx][1]
          known_end = timestamps[idx][1];
          timespan = known_end - known_start
          for i in range(1, questionmarkcounter + 1):
            new_timestamp = known_start + (i * timespan / (questionmarkcounter + 1))
            new_timestamp = int(new_timestamp*100)/100
            fix_idx = known_start_idx + i
            timestamps[fix_idx][1] = new_timestamp
          questionmarkcounter = 0
        
      # Expand the "endstart" entries to two separate
      # entries
      for idx in range(len(timestamps) - 1, 0, -1):
        if timestamps[idx][0] == "endstart":
          timestamps[idx][0] = "end"
          timestamps.insert(idx +1, ["start", timestamps[idx][1], timestamps[idx][2] + 1])

      # Restructure the timestamps to be more handy
      timestamp_lines = [{"intra": []}]
      last_line = 0
      for ts in timestamps:
        if ts[2] > last_line:
          timestamp_lines.append({"intra": []})
          last_line = ts[2]
        if ts[0] == "start":
          timestamp_lines[ts[2]]["start"] = ts[1]
          timestamp_lines[ts[2]]["intra"].append(ts[1])
        if ts[0] == "end":
          timestamp_lines[ts[2]]["end"] = ts[1]
          timestamp_lines[ts[2]]["intra"].append(ts[1])
        if ts[0] == "intra":
          timestamp_lines[ts[2]]["intra"].append(ts[1])

      for line_idx in range(len(card)):
        # We may have a gap between the ending of the last line and
        # the start of this one. On the first line of the card this
        # was taken care of in self.layout(), evaluating the respective
        # pre gap.
        if (line_idx > 0 and  timestamp_lines[line_idx]["start"] - timestamp_lines[line_idx - 1]["end"] > self.cue_length):
          display_type = "cue"
        
        clean_and_split_line = self.clean_and_split_line(card[line_idx])
        cleaned_line = clean_and_split_line["line"]
        line_parts = clean_and_split_line["parts"]
        line_def = {
          "text": cleaned_line,
          "slot": line_idx,
          "display": item["display"],
          "show": item["show"],
          "hide": item["hide"],
          "start": timestamp_lines[line_idx]["start"],
          "end": timestamp_lines[line_idx]["end"],
          "parts": False,
          "card": item["card"]
        }
        if len(line_parts) > 1:
          line_def["parts"] = []
          for i in range(len(line_parts)):
            line_def["parts"].append({
              "text": line_parts[i],
              "slot": line_idx,
              "start": timestamp_lines[line_idx]["intra"][i],
              "end": timestamp_lines[line_idx]["intra"][i + 1]
            })
        self.data["lines"].append(line_def)
        item["display"] = "regular"

      if item["peek"] and not item["card"] == len(self.data["cards"]) - 1:
                          # never after the last card
        preek_line =  clean_and_split_line = self.clean_and_split_line(self.data["cards"][item["card"] + 1][0])["line"]
        self.data["lines"].append({
          "text": preek_line,
          "slot": line_idx + 1,
          "display": "peek",
          "show": item["show"],
          "hide": item["hide"],
        }) 

  def clean_and_split_line(self, text):
    """
      Get rid of any timestamps in the line, but return the parts of
      breaking the the line at intra timestamps
    """
    text = re.sub("\[.*?\]", "[", text)
    if text[0] == "[":
      text = text[1:]
    if text[len(text) - 1] == "[":
      text = text[:-1]
    parts = text.split("[")
    text = re.sub("\[", "", text)
    return {"line": text, "parts": parts}
    
  def drawBackground(self):
    rect = pygame.Rect(0, 0, self.width, self.height)
    pygame.draw.rect(self.screen, self.bgcolor, rect)

  def parse(self, filename):
    """
      Parse the cards and give helpful errors if something's wrong.
      Additionally timestamps within text are rewritten to be easily
      handled in the subsequent layout step.
    """
    # Keep track of the line we're processing
    linecount = 0
    
    # Read the file contents into memory
    txt = self.file_get_contents(filename)
    
    # Parse the configuration line, which is the first line of the file
    cards = txt.split("--")
    d = re.match("#\s+Duration:\s" + self.tsRegex, cards[0])
    if d:
      d_sec = d.group(2)
      d_min = d.group(1)
      duration = float(d_sec);
      if (d_min != None):
        duration += float(d_min)*60
      self.data["duration"] = duration
    else:
      raise ParserError(linecount + 1, "Failed to parse duration timestamp.")      
   
    del cards[0] # Get rid of the "configuration card"
      
    # Iterate over the cards
    for card in cards:
      # Strip whitespace from all the lines on the card
      lines = list(map(lambda i: i.strip(), card.split("\n")))
      if '' == lines[-1]:
        del lines[-1] # There's certainly a \n afer the last line of the
                      # card, which yields an empty last list item.
      ts_match = re.match("\s*" + self.tsRegex + "\s*-\s*" + self.tsRegex, lines[0])

      if ts_match:
        start = float(ts_match.group(2))
        if (ts_match.group(1) != None):
          start += float(ts_match.group(1)) * 60        
        end = float(ts_match.group(4))
        if (ts_match.group(3) != None):
          end += float(ts_match.group(3)) * 60    
        self.data["timestamps"].append((start,end))
      
        del lines[0] # Get rid of the seperator line
        linecount += 1 # + 1 for the seperator line
        
        # Scan the lines for intra line timestamps and check them for
        # sensible timings.
        for line_idx in range(len(lines)):
          linecount += 1
          line = lines[line_idx]
          last_ts = start
          intra_search = re.finditer("\[" + self.tsRegex + "\]", line)
          for intra_match in intra_search:
            secs = float(intra_match.group(2))
            if (intra_match.group(1) != None):
              secs += float(intra_match.group(1)) * 60   
            if not last_ts <= secs <= end:
              raise ParserError(linecount + 1, "Timestamp out of bounds:'" + line + "'")
            last_ts = secs 
            # Replace the timestamps with their parsed version.
            lines[line_idx] = lines[line_idx].replace(intra_match.group(0), "[" + str(secs) + "]")
        self.data["cards"].append(lines)
      else:
        raise ParserError(linecount + 1, "No timestamps")
      
  def updateFont(self):
    """ 
      This not only updates the font definition in use, but also
      recalculates the lineheight.
    """
    self.font = pygame.font.Font(self.fontfile, self.fontSize)
    text = self.font.render("a", True, (0,0,255))
    self.lineheight = text.get_rect().h

  # Hello php-folks!
  def file_get_contents(self, filename):
    """ Return the contents of the given file in a single string. """
    with open(filename) as f:
      return f.read()
        
  def debug_output(self):
    """
      Print a parsed version of the input file to stdout.
    """
    print("# Duration: " + str(self.data["duration"]))
    lastcard = -1
    for l in self.data["lines"]:
      if l["display"] == "peek" or l["display"] == "pause": continue
      if lastcard != l["card"]:
        timestamps = self.data["timestamps"][l["card"]]
        print("-- %.2f - %.2f" % (timestamps[0], timestamps[1]))
      if l["parts"] == False:
        start = "%.2f" % l["start"]
        end = "%.2f" % l["end"]
        print("[" + start + "]" + l["text"] + "[" + end + "]")
      else:
        start = "%.2f" % l["parts"][0]["start"]
        outstr = "[" + start + "]"
        for p in l["parts"]:
          end = "%.2f" % p["end"]
          outstr += p["text"] + "[" + end + "]"
        print(outstr)
      lastcard = l["card"]

  def show_plug(self):
      text = self.font.render("kara-okay.github.io", True, self.peekcolor)
      textrect = text.get_rect()
      textrect.midbottom = (self.width/2, self.height - self.lineheight * 0.5) 
      self.screen.blit(text, textrect)

if __name__ == "__main__":  
  parser = argparse.ArgumentParser(description='Produce an okay karaoke movie from a text file. See README.md.')
  parser.add_argument("filename", help = "Input file to process. May be ending with .kok.")
  parser.add_argument("-o", "--outfile", dest = "outfile", help = "Name of the movie file. it should end in .mp4. If none given, a filename is guessed from the input file.")
  parser.add_argument("-a", "--audiofile", dest = "audiofile", help = "Path to the audio file to play in the movie. If none given, the movie remains silent.")
  parser.add_argument("-f", "--fontfile", dest = "fontfile", help = "Path to a font file usable by pygame. Defaults to ./fonts/SourceSansPro-Semibold.ttf")
  parser.add_argument("--force", action = "store_true", help = "If set, an existing movie may be overriden.")
  parser.add_argument("--debug", action = "store_true", help = "If set, the current time is rendered on every frame and the text with timings is printed to stdout.")
  parser.add_argument("--suppress-plug", action = "store_true", help = "If set, the plug after the last slide will not be shown.")
  args = parser.parse_args()

  app = KaraOkay(args.filename, args.outfile, args.audiofile, args.fontfile, args.force, args.debug, args.suppress_plug)
  app.run()  


