#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Sep 23 20:44:45 2021

@author: Alex Boisvert

Query the database for anagram solving
"""
import mysql.connector
import re
import string
import os
import argparse

NUM_ANAGRAMS = 50
ALPHABET = string.ascii_lowercase

def db_connection():
    # Connect to DB
    ODBC_FILE = os.path.join(os.path.expanduser('~'),os.path.join('.odbc','ANAGRAM.odbc'))
    dsn_dict = dict()
    with open(ODBC_FILE,'r') as fid:
        for line in fid.readlines():
            if '=' in line and not line.startswith('#'):
                prop,val = [_.strip() for _ in line.split('=')]
                dsn_dict[prop] = val
                
    mydb = mysql.connector.connect(
      host="localhost",
      user=dsn_dict['USER'],
      passwd=dsn_dict['PASS'],
      database=dsn_dict['DB']
    )
    return mydb


def get_anagrams(anagram_string, results_limit=NUM_ANAGRAMS):
    """
    Get the anagrams from the string
    """
    # Remove anything but letters and question marks from the string
    anagram_string = re.sub(r'[^a-z\?]+', '', anagram_string.lower())
    as_len = len(anagram_string)
    # We test for equality unless there's a question mark
    comparison_sign = ' = '; skip_zeros = False
    if '?' in anagram_string:
        comparison_sign = ' >= '
        skip_zeros = True
    and_array = []
    for let in ALPHABET:
        letter_count = anagram_string.count(let)
        if skip_zeros and letter_count == 0:
            continue
        q_tmp = f' AND {let}_ct {comparison_sign} {letter_count}'
        and_array.append(q_tmp)
    # add in a length restriction
    and_array.append(f' AND `length` = {as_len}')
    query_where = '\n'.join(and_array)
    query = f'''
    SELECT word
    FROM anagrammer
    WHERE 1=1
    {query_where}
    ORDER BY `score` DESC
    LIMIT {results_limit}
    '''
    mydb = db_connection()
    cur = mydb.cursor()
        
    cur.execute(query)
    res = cur.fetchall()
    mydb.disconnect()
    return [x[0] for x in res]
    
#END get_anagrams()

#%%
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Read in a string to anagram.')
    parser.add_argument('--str', type=str, help='The string to anagram.  Use ? for unknown letters.')
    args = parser.parse_args()
    anagrams = get_anagrams(args.str)
    print(anagrams)
        