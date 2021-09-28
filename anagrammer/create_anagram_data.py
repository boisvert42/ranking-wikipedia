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
# the maximum length of words we take
MAX_LENGTH = 50
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
        if len(alphagram) > MAX_LENGTH:
            continue
        if len(word) > MAX_LENGTH:
            continue
        mylen = len(alphagram)
        letter_counts = []
        for let in ALPHABET:
            letter_counts.append(alphagram.count(let))
        row = [word, alphagram, mylen] + letter_counts + [score]
        data.append(row)

data_orig = copy.copy(data)

#%%
# We keep a word if it passes the min score threshold
# or if it's one word
MIN_SCORE = 50

letter_count_columns = []
for let in ALPHABET:
    letter_count_columns.append(f'{let}_ct')
columns = ['word', 'alphagram', 'length'] + letter_count_columns + ['score']

data = copy.copy(data_orig)
df = pd.DataFrame(data=data, columns=columns)
df_orig = df.loc[(df['score'] >= MIN_SCORE) | (df['word'].str.isalpha())]
print(len(df_orig))
#%%
#df.to_csv('anagrammer.csv', index=False, header=False)
#df.to_json('anagrammer.json')
# Create a ginormous insert statement
# Sanitize single-quotes
df1 = df_orig.copy()
df1['word'] = df1['word'].apply(lambda x: x.replace("'", r"\'"))
# Create an VALUES string for each row
values_series_orig = df1.apply(lambda row: f"('{row[0]}','{row[1]}',{','.join(map(str, row[2:]))})", axis=1)
#%%
values_series = copy.deepcopy(values_series_orig)
NUM_VALUES = 40000
q = ''
while len(values_series):
    vs_tmp, values_series = values_series[:NUM_VALUES], values_series[NUM_VALUES:]
    q += '''INSERT INTO `anagrammer` VALUES\n'''
    q += ','.join(vs_tmp)
    q += ';\n'

with open('insert_data.sql', 'w') as fid:
    fid.write(q)