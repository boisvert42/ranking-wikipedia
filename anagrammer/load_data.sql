LOAD DATA INFILE 'C:\\ProgramData\\MySQL\\MySQL\ Server\ 8.0\\Uploads\\anagrammer.csv' INTO TABLE anagrammer.anagrammer
FIELDS TERMINATED BY ',' ENCLOSED BY '"'
/* note: this should be just '\n' on OSX / Linux */
LINES TERMINATED BY '\r\n'
STARTING BY '';
