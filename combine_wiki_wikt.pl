#!/usr/bin/perl -w
use strict;

my $wiki_file = 'RankedWiki.txt';
my $wikt_file = 'RankedWiktionary.txt';
my @files = ($wiki_file, $wikt_file);

my %dict;
for my $file (@files)
{
    open FILE, $file or die $!;
    while (<FILE>)
    {
        chomp;
        my ($word,$score) = ($_ =~ /^(.*)@(.*)$/);
        if ($dict{$word})
        {
            $dict{$word} = $score if $score > $dict{$word};
        }
        else {$dict{$word} = $score;}
    }
    close FILE;
}

open OUTFILE, '>RankedWikiWikt.txt' or die $!;
foreach (sort { ($dict{$b} <=> $dict{$a}) || ($a cmp $b) } keys %dict)
{
    print OUTFILE $_ . "\@" . $dict{$_} . "\n";
}

close OUTFILE;
