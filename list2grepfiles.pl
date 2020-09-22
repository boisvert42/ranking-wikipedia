#!/usr/bin/perl -w

use strict;
use Data::Dumper;

my $rankedwikifile = $ARGV[0];
my $rankedwikiwiktfile = $ARGV[1];

my %files = ($rankedwikifile => 'Wiki.txt',
            $rankedwikiwiktfile => 'WikiWikt.txt'
            );

while (my ($f,$g) = each(%files))
{
    open FILE, $f or die $!;
    open OUTFILE, ">$g" or die $!;
    while (<FILE>)
    {
        my ($orig,$score) = ($_ =~ /^(.*)@(.*)$/);
        last if $score < 30;
        if ($orig =~ /(.*) \(.*$/) {$orig = $1;}
        (my $tx = $orig) =~ s/[^A-Za-z0-9]//g;
        print OUTFILE "$tx\%$orig\@$score\n";
    }
    close FILE;
    close OUTFILE;
}
