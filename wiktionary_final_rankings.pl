#!/usr/bin/perl -w

use strict;

use Storable qw (nstore retrieve);
use Statistics::Descriptive;
use Time::Piece;

use Data::Dumper;
use warnings;

###########################################################################
# %wiki is a hash where keys are lowercase unaccented Wikipedia page titles.
# Values are:
#       - Original -- the original page title with proper uppercase (no accents, for now)
#       - NumberInLinks -- the number of links to the page
#       - NumberLanguages -- the number of languages the page is translated to
#       - PageLength -- the length of the article
#       - LastUpdated -- the Unix timestamp of the last update
###########################################################################

my $wiki_storable = $ARGV[0] or die $!;

my $t = localtime;
my $outfile = "RankedWiktionary" . $t->strftime("%b%Y") . ".storable";

my $g = retrieve($wiki_storable);

# Remove anything with no summary
# Taking out for now
#my %wiki = map {$g->{$_}->{'Summary'} ? ($_, $g->{$_}) : ()} keys %$g;
#$g = \%wiki;

my %fields = ('NumberInLinks' => 100);

my %final_rankings = rank_wiki($g,\%fields);


## Rank Norvig's list and include this information
my $norvig = 'google-books-common-words.txt';
my %nvg;
my @vals;
if (-e $norvig) 
{
    open NVG, $norvig or die "Couldn't find $norvig";
    while (<NVG>)
    {
        chomp;
        my ($w,$s) = ($_ =~ /^(.*)\t(.*)$/);
        $nvg{lc $w} = $s;
        push(@vals,$s);
    }
    close NVG;
}
else 
{
    warn "Norvig file not found -- can be downloaded from http://norvig.com/google-books-common-words.txt";
}

# Find percentiles
my @pcts = get_percentiles(\@vals,100);

# Go through the original list and re-rank some entries
foreach my $orig (keys %final_rankings)
{
    # Change the score for Norvig words
    if ($nvg{$orig})
    {
        my $score = $final_rankings{$orig}{'Score'};
        my $score2 = get_score2(\%nvg,$orig,\@pcts);
        if ($score2 > $score) {$final_rankings{$orig}{'Score'} = $score2;}
    }
}

# Add in rankings for plurals
foreach my $orig (keys %final_rankings)
{
    # Add in scores for plurals
    if ($g->{$orig}->{'PluralOf'})
    {
        my $singular = $g->{$orig}->{'PluralOf'};
        if ($final_rankings{$singular}{'Score'})
        {
            $final_rankings{$orig}{'Score'} = $final_rankings{$singular}{'Score'};
        }
        else {$final_rankings{$orig}{'Score'} = 0;}
    }
}

# Remove anything without a score
%final_rankings = map {$final_rankings{$_}{'Score'} ? ($_, $final_rankings{$_}) : ()} keys %final_rankings;

my $tt = localtime(time);
my $monYr = $tt->strftime("%b%Y");

## Write out the RankedWiktionary.txt file
my $outText = 'RankedWiktionary' . $monYr . '.txt';
open RW, ">$outText" or die $!;
foreach (sort { ($final_rankings{$b}{'Score'} <=> $final_rankings{$a}{'Score'}) || ($a cmp $b) } keys %final_rankings)
{
    print RW $_ . "\@" . $final_rankings{$_}{'Score'} . "\n";
}
close RW;

nstore \%final_rankings, $outfile;

######
# SUBS
######

sub rank_wiki
{
    my %ranked;
    my $g = shift;
    my $fields = shift;
    my $ctr = 0;
    foreach my $field (keys %fields)
    {
        # Set up array for the key
        my @valarray = get_value_array($g,$field);
        # Set up percentiles
        my @pctiles = get_percentiles(\@valarray,$fields->{$field});
        # Loop (ugh) through $g to assign a score to each element
        foreach my $page (keys %$g)
        {
            $ranked{$g->{$page}->{'Original'}}{'Score'} += get_score($g,$page,$field,\@pctiles);
            # We only need to do this once
            if ($ctr == 0)
            {
                #$ranked{$g->{$page}->{'Original'}}{'Blob'} = $g->{$page}->{'Summary'};
                $ranked{$g->{$page}->{'Original'}}{'ToXword'} = ToXword($g->{$page}->{'Original'});
            }
        }
        $ctr = 1 if $ctr == 0;
    }
    return %ranked;
}
                       
sub get_score
{
    my $g = shift;
    my $page = shift;
    my $field = shift;
    my $pctiles = shift;
    my $sz = @$pctiles;
    my $score = $sz - 1;
    while ($g->{$page}->{$field} < $pctiles->[$score] && $score >= 0)
    {
        $score--;
    }
    return $score;
}

sub get_score2
{
    my $g = shift;
    my $page = shift;
    my $pctiles = shift;
    my $sz = @$pctiles;
    my $score = $sz - 1;
    while ($g->{$page} < $pctiles->[$score] && $score >= 0)
    {
        $score--;
    }
    return $score;
}

sub get_value_array
{
    my $g = shift;
    my $txt = shift;
    my @array;
    foreach my $k (keys %$g)
    {
        if ($g->{$k}->{$txt}) {push(@array,$g->{$k}->{$txt});}
        else {push(@array,0);}
    }
    return @array;
}

sub get_percentiles
{
    my $dt = shift;
    my $weight = shift;
    my @data = @$dt;
    my $stat = Statistics::Descriptive::Full->new();
    $stat->add_data(@data);
    my @Pctile = (0);
    my $a = 100/sqrt($weight + 1);
    for (my $i = 1; $i<=$weight; $i ++)
    {
        #my $pct = $stat->percentile(100*$i/($weight+1));
        # Let's try doing this on a non-linear scale
        my $pct = $stat->percentile($a * sqrt($i));
        push(@Pctile,$pct);
    }
    return @Pctile;
}

sub ToXword
{
    my $w = shift;
    $w = uc $w;
    $w =~ s/[^A-Z0-9]//g;
    return $w;
}
