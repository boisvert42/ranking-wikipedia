#!/usr/bin/perl -w

use strict;
use Data::Dumper;

my $rankedwikifile = $ARGV[0];
my $rankedwikiwiktfile = $ARGV[1];

my @rankedWikiFiles = qw/Wiki.txt/;
my @rankedWikiWiktFiles = qw/WikiWikt.txt WikiWiktJS.txt/;

my %files = ($rankedwikifile => \@rankedWikiFiles,
            $rankedwikiwiktfile => \@rankedWikiWiktFiles
            );

while (my ($f,$g) = each(%files))
{
    foreach my $outfile (@$g) {
        open OUTFILE, ">$outfile" or die $!;
        my $minScore = 30;
        if ($outfile =~ /JS/) {$minScore = 70;}
        open FILE, $f or die $!;
        while (<FILE>)
        {
            my ($orig,$score) = ($_ =~ /^(.*)@(.*)$/);
            last if $score < $minScore;
            if ($orig =~ /(.*) \(.*$/) {$orig = $1;}
            (my $tx = $orig) =~ s/[^A-Za-z0-9]//g;
            print OUTFILE "$tx\%$orig\@$score\n";
        }
        open FILE, $f or die $!;
        close OUTFILE;
    }
}
