#!/usr/bin/perl -w

use strict;

use Storable qw (nstore retrieve);
use Statistics::Descriptive;
use Time::Piece;

use warnings;

use JSON;

###########################################################################
# Make a JSON object of noun -> [plurals of noun]
###########################################################################

my $wiki_storable = $ARGV[0] or die $!;

my $t = localtime;
my $outfile = "plurals.json";

my $g = retrieve($wiki_storable);

my %fields = ('NumberInLinks' => 100);

my %final_rankings = rank_wiki($g,\%fields);

# Process plurals
my %plurals;
foreach my $orig (keys %final_rankings)
{
    #print "$orig\n";
    if ($g->{$orig}->{'PluralOf'})
    {
        foreach my $singular (@{$g->{$orig}->{'PluralOf'}})
        {
            if ($plurals{$singular}) 
            {
                my $found = grep $_ eq $orig, @{$plurals{$singular}};
                if ($found == 0)
                {
                    #print $plurals{$singular} . "\n";
                    push(@{$plurals{$singular}},$orig);
                }
            }
            else
            {
                @{$plurals{$singular}} = ($orig);
            }
        }
    }
}

my $json_text = encode_json \%plurals;
#print $json_text;

open RW, ">$outfile" or die $!;
print RW $json_text;
close RW;

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
