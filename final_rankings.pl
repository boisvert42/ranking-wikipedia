#!/usr/bin/perl -w

use strict;

use Storable qw (nstore retrieve);
use Statistics::Descriptive;
use Unicode::Normalize;
use Time::Piece;

use Data::Dumper;

###########################################################################
# %wiki is a hash where keys are lowercase unaccented Wikipedia page titles.
# Values are:
#       - Original -- the original page title with proper uppercase (no accents, for now)
#       - NumberInLinks -- the number of links to the page
#       - PageLength -- the length of the article
#       - Summary is a summary of the article
#       - Name is 1 if it is a name, 0 otherwise
###########################################################################

my $wiki_storable = $ARGV[0] or die $!;

my $g = retrieve($wiki_storable);

my %fields = ('NumberInLinks' => 70, 'PageLength' => 30);

my %final_rankings = rank_wiki($g,\%fields);

# # Need to consolidate pages that end in parentheses
# foreach my $title (keys %final_rankings)
# {
    # # Only look for titles with parentheses at the end
    # if ($title =~ /^(.*) \([^\)]+\)$/)
    # {
        # my $new_title = $1;
        # if (!exists $final_rankings{$new_title} || $final_rankings{$new_title}{'Score'} < $final_rankings{$title}{'Score'})
        # {
            # $final_rankings{$new_title}{'Score'} = $final_rankings{$title}{'Score'};
            # #$final_rankings{$new_title}{'Blob'} = $final_rankings{$title}{'Blob'};
            # $final_rankings{$new_title}{'ToXword'} = ToXword($new_title);
            # $final_rankings{$new_title}{'OrigTitle'} = $title;
            # $final_rankings{$new_title}{'Name'} = $final_rankings{$title}{'Name'};
        # }
        # # We always want to delete the titles with parentheses at the end
        # delete($final_rankings{$title});
    # }
# } # end foreach title

my $t = localtime(time);
my $monYr = $t->strftime("%b%Y");

# Write RankedWiki.txt and FamousNames.txt
my $outText = 'RankedWiki.txt';
open NAMES, '>FamousNames.txt' or die $!;
open RW, ">$outText" or die $!;
foreach (sort { ($final_rankings{$b}{'Score'} <=> $final_rankings{$a}{'Score'}) || ($a cmp $b) } keys %final_rankings)
{
    print RW $_ . "\@" . $final_rankings{$_}{'Score'} . "\n";
    if ($final_rankings{$_}{'Score'} >= 80 && $final_rankings{$_}{'Name'} == 1)
    {
        print NAMES $_ . "\t" . $final_rankings{$_}{'Score'} . "\n";
    }
}
close RW;
close NAMES;

my $outFile = 'RankedWiki' . $monYr . '.storable';
nstore \%final_rankings, $outFile;

######
# SUBS
######

sub remove_diacritics
{
    my $w = NFD(shift);
    $w =~ s/\pM//g;
    return $w;
}

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
        foreach my $pg (keys %$g)
        {
            my $page = $pg;
            my $title = $g->{$page}->{'Original'};
            # If this page is a redirect, we need to change the "$page" variable
            # NOTE: For now, we just skip these.
            # TODO: find a better way to handle them.
            next if ($g->{$page}->{'REDIRECT'});
            # {
            # my $text = $g->{$page}->{'REDIRECT'};
            # print "$page $text\n";
            # next if $text =~ /\{\{/;
            # if ($text =~ /[[([^\]\:+)]]/) {$page = lc remove_diacritics($1);}
            # else {next;}
            # next unless $g->{$page};
            # }
            $ranked{$title}{'Score'} += get_score($g,$page,$field,\@pctiles);
            # We only need to do this once
            if ($ctr == 0)
            {
                #$ranked{$title}{'Blob'} = $g->{$page}->{'Summary'};
                $ranked{$title}{'ToXword'} = ToXword($title);
                $ranked{$title}{'Name'} = $g->{$page}->{'Name'};
            }
        }
        $ctr++;
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
    return 0 unless $g->{$page}->{$field};
    while ($g->{$page}->{$field} < $pctiles->[$score] && $score >= 0)
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
