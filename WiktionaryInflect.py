#!/usr/bin/python
"""
WiktionaryInflect.py

Take the RankedWiktionary list and add inflected forms
"""

import lemminflect
import itertools

# The points we remove for scores of inflected forms
INFLECTED_PENALTY = 5

rw = dict()
with open('RankedWiktionaryNoInflections.txt', 'r') as fid:
	for line in fid:
		line = line.strip()
		word, score = line.split('@')
		score = int(score)
		rw[word] = score

# Go through inflected forms and add them
rw2 = dict()
for word, score in rw.items():
	infl = lemminflect.getAllInflections(word)
	for word1 in itertools.chain(*infl.values()):
		try:
			rw[word1]
		except:
			rw2[word1] = max(1, score - INFLECTED_PENALTY)

# Extend the dictionary
rw.update(rw2)

# Write the list
with open('RankedWiktionary.txt', 'a') as fid:
	for word, score in rw.items():
		fid.write(f'{word}@{score}\n')
