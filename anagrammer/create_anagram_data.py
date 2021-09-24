#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Make anagram database from Ranked Wiki data

@author: Alex Boisvert
"""

import pandas as pd
import string
import re
import copy

ALPHABET = string.ascii_lowercase

def compute_alphagram(s):
    """
    Return the letters of s, sorted, alpha-only, all lowercase
    """
    s_alpha_only = re.sub(r'[^A-Za-z]+', '', s.lower())
    return ''.join(sorted(s_alpha_only))

#%%
data = []
words = set()
# Read in our data
with open(r'RankedWikiWikt.txt', 'r') as fid:
    for line in fid:
        line = line.strip()
        word, score = line.split('@')
        # Get rid of trailing parentheses
        if ' (' in word:
            ix = word.index(' (')
            word = word[:ix]
        # Don't add this if we already have it
        word_lower = word.lower()
        if word_lower in words:
            continue
        else:
            words.add(word_lower)
        # Throw out anything with a number
        if re.search(r'\d', word) is not None:
            continue
        score = int(score)
        # Get the alphagram and the length
        alphagram = compute_alphagram(word)
        # throw out anything of length > 100
        if len(alphagram) > 100:
            continue
        mylen = len(alphagram)
        letter_counts = []
        for let in ALPHABET:
            letter_counts.append(alphagram.count(let))
        row = [word, alphagram, mylen] + letter_counts + [score]
        data.append(row)
        
data_orig = copy.copy(data)

#%%
letter_count_columns = []
for let in ALPHABET:
    letter_count_columns.append(f'{let}_ct')
columns = ['word', 'alphagram', 'length'] + letter_count_columns + ['score']

data = copy.copy(data_orig)
df = pd.DataFrame(data=data, columns=columns)
df = df.loc[df['score'] >= 30]
print(len(df))
df.to_csv('anagrammer.csv', index=False, header=False)
#df.to_json('anagrammer.json')
