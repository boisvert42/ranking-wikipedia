# ranking-wikipedia
Perl scripts to rank Wikipedia page titles

This collection of Perl scripts will create files of ranked WIkipedia pages along the lines of those at http://crosswordnexus.com/wiki.  To use:

1. Download and extract https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles.xml.bz2
2. Download and extract https://dumps.wikimedia.org/enwiktionary/latest/enwiktionary-latest-pages-articles.xml.bz2
3. Run perl WikiExtract.pl to create WikiMonYr.storable
4. Run perl WiktionaryExtract.pl to create WiktionaryMonYr.storable
5. Run perl final_rankings.pl WikiMonYr.storable to create RankedWiki.txt and FamousNames.txt
6. Run perl wiktionary_final_rankings.pl WiktionaryMonYr.storable to create RankedWiktionary.txt
