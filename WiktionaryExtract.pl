#!/usr/bin/perl -w

use strict;

use Parse::MediaWikiDump;
use Text::MediawikiFormat as => 'wiki2html';
use Unicode::Normalize;
use Time::Piece;
use Data::Dumper;
use Storable qw (nstore retrieve);

import JSON;

# I get tons of utf-8 warnings running this.
# The problem appears to be in the get_links subroutine.
# I should probably fix it but I don't know how, so:
no warnings 'utf8';

###########################################################################
# %wiki is a hash where keys are lowercase unaccented Wikipedia page titles.
# Values are:
#	- Original -- the original page title with proper uppercase (no accents, for now)
#	- NumberInLinks -- the number of links to the page
#	- NumberLanguages -- the number of languages the page is translated to
#		- Number Languages is currently unused
#	- PageLength -- the length of the article
#	- LastUpdated -- the Unix timestamp of the last update
#	- Summary: HTML'ed summary of the page's contents
###########################################################################
my %wiki;

my $t = localtime;
my $outfile = "Wiktionary" . $t->strftime("%b%Y") . ".storable";

my $xmlfile = "enwiktionary-latest-pages-articles.xml";
my $pages = Parse::MediaWikiDump::Pages->new($xmlfile);

# Go through the XML and pull out interesting entries.
while(defined(my $page = $pages->next))
{
	#main namespace only
	next unless $page->namespace eq '';

	# Weed out anything unimportant
	next if defined($page->redirect);

	# If we've gotten this far we can proceed
	my $title = $page->title;

	# TEMP
	#next unless $title eq 'color';

	# Make sure the title is "interesting"
	# This includes making sure the word is only lowercase
	next unless is_interesting_title($title);

	# NOTE: the title should be all lowercase with no diacritics anyway
	# but it doesn't hurt to leave this in.
	my $rd_title = remove_diacritics($title);
	my $lc_title = lc $rd_title;

	$wiki{$lc_title}{'Original'} = $rd_title;

	# Get stuff related to the article text
	my $text = $page->text; # This is just a reference

	# Get the length of the articles
	my $length = get_length($text);

	$wiki{$lc_title}{'PageLength'} = $length;

	# Get a summary of the page
	my $summary = get_html_summary($text);
	$wiki{$lc_title}{'Summary'} = $summary;

    # If this title is a plural, add an inlink
    # Also note what the original was
    if ($$text =~ /\{\{plural of\|(.*?)\|lang=en\}\}/ || $$text =~ /plural of\|(.*?)\}\}/)
    {
        my $singular = $1;
        $wiki{$lc_title}{'NumberInLinks'}++;
        push(@{$wiki{$lc_title}{'PluralOf'}},$singular);
    }

    # If this is a noun, add the plurals that way
    # Example: {{en-noun|deer|deers|pl2qual=nonstandard}}
    if ($$text =~ /\{\{en-noun\|(.*?)\}\}/)
    {
        my $plural_string = $1;
        my @plurals = split(/\|/,$1);
        foreach my $pl (@plurals)
        {
            if ($pl !~ /=/)
            {
                my $rd_pl = remove_diacritics($pl);
                my $lc_pl = lc $rd_pl;
                push(@{$wiki{$lc_pl}{'PluralOf'}},$lc_title);
            }
        }
    }

	# Update inlinks counter for *other* (linked) articles
	my %links = get_links($text);
	foreach my $ttl (keys %links)
	{
		# Note: this title is already in lowercase and without accents
		$wiki{$ttl}{'NumberInLinks'}++;
	}

	#print $wiki{$lc_title}{'Summary'};
	#print Dumper(\%wiki);
	#die;

}

# Remove any hash elements that are just inlinks
%wiki = map {$wiki{$_}{'Original'} ? ($_, $wiki{$_}) : ()} keys %wiki;

# Remove anything with no inlinks at all
%wiki = map {$wiki{$_}->{'NumberInLinks'} ? ($_, $wiki{$_}) : ()} keys %wiki;

# Remove anything with no summary
%wiki = map {$wiki{$_}->{'Summary'} ? ($_, $wiki{$_}) : ()} keys %wiki;

# Hooray!  Send this to a storable so another perl script can process it.
nstore \%wiki, $outfile;

# Save JSON File
my $jsonOutfile = 'Wiktionary' . $monYr . '.json';
write_file($jsonOutfile, encode_json(\%wiki));

######
# SUBS
######

# Remove diacritics and put a title in lowercase
sub lowercase_title
{
	my $t = shift;
	return lc remove_diacritics($t);
}

# Remove diacritics (from a title)
sub remove_diacritics
{
   my $w = NFD(shift);
   $w =~ s/\pM//g;
   return $w;
}

# Boolean to determine if an article is interesting JUST from the title.
# ARB modified 2/27/2012 to allow numbers
# NOTE: We don't allow pages with parentheses in the title
#Usage: $goodYN = is_interesting_title($t)
sub is_interesting_title
{
	my $t = shift;

	# 3/8/2012 changed the "good" characters list
	return
	(
	$t =~ /^[a-z0-9\s]+$/  # Title contains no "bad" characters
	&& length($t) <= 50  # Title isn't too long
	&& length(ToXword($t)) >= 3 # Title can't be too short
	);
}

sub get_plurals
{
	# Get plurals of a word
	my ($txt,$title) = @_;
	my $text = $$txt;

	if ($text =~ /\{\{en-noun\|(.*?)\}\}/)
	{
		my $list = $1;
		my @plurals = split(/\|/,$list);
		my $c = 0;
		my @final;
		foreach my $p (@plurals)
		{
			next unless $p =~ /^[a-z ]+$/;
			if ($p eq 's') {$p = $title . 's';}
			$c++;
			push(@final,$p);
		}
		return join("\t",@final);
	}
    elsif ($text =~ /\{\{en-noun\}\}/)
    # If there is only one plural and it is standard, wiktionary presents it like this.
    {
        return $title . 's';
    }
}


# Return the list of links from a given page
# Note: this returns a hash to avoid double counting
# Usage: %links = get_links($text)
sub get_links
{
    my $text = shift;
    $text = $$text;
    # Remove newlines
    $text =~ s/[\r\n]//g;
    my %links;
    # We try to exclude links to different namespaces
    # We also have to grab only stuff before a pipe
    # Should we exclude anything between curly brackets for this purpose?
    #		- I think we should.
    while ($text =~ /^(.*?)\{\{[^\}]+\}\}(.*)$/) {$text = $1.$2;}
    while ($text =~ /.*?\[\[([^\|\:\]]+)[\|]{0,1}[^\}\:\]]*\]\](.*)$/)
    {
    	# Only add the link if it's an "interesting" one per our definition
    	# We MUST add the lowercase version to avoid double counting
    	my $title = $1;
    	$text = $2;
    	if (is_interesting_title($title)) {$links{lowercase_title($1)} = 1;}
    }
    return %links;
}

# Grab the length of an article.
# This is intended to exclude external URLs.
# Usage: $len = get_length($text)
sub get_length
{
    my $text = shift;
    $text = $$text;
    # Remove newlines and whitespace.
    # Don't know why newlines are a problem.
    $text =~ s/\s//g;
    # Remove anything between two curly brackets
    while ($text =~ /^(.*?)\{\{[^\}]+\}\}(.*)$/) {$text = $1.$2;}
    # Something else to whittle down the text here, maybe
    return length($text);
}

sub get_html_summary
{
	# Get a summary of the article from the text
	# This will just be the first paragraph.
	# We need to remove the junk and make it HTML.
	my ($txt) = @_;
	my $text = $$txt;
	# Remove the junk (anything between {{ and }})
	# Thank you http://stackoverflow.com/questions/5410652/regex-delete-contents-of-square-brackets
	$text =~ s/\{\{([^\{\}]|(?0))*\}\}//gs;
	# Remove anything that is HTML commented
	$text =~ s/<\!--[^>]*-->//gs;
	# Remove anything within a "ref"
	$text =~ s/\<ref.*?\<\/ref\>//g;
	# Sometimes images get in front of the text.  Delete all that.
	$text =~ s/^\s*\[\[.*?\]\]\n//gs;
	# Remove any blank characters from the beginning
	$text =~ s/^[\s\r\n]*//gs;
	# Remove any links with a colon in them
	# This does one-level recursion just in case
	$text =~ s/\[\[[^\]]+\:([^\[\]]|(\[\[[^\]]+\]\]))*\]\]//gs;
	# Remove diacritics
	$text = remove_diacritics($text);

	# Remove any lines starting with #*
	$text =~ s/\#\*[^\n]*\n//gs;
	# Remove any essentially empty definitions
	$text =~ s/\#[\W]*\n//gs;

	# Prune this a bit
	# Add a fake language to the end
	$text = "$text\n==FakeLang==\n";

	# Only keep the "English" part
	# If there isn't an "English" part we skip
	if ($text =~ /==English==(.*?)\n==[^=]+==\n/s)
	{
		$text = $1;
	} else {return '';}

	# Add a fake part of speech to the end
	$text = "$text\n===FakePOS===\n";

	# Grab certain parts of speech:
	# Noun, Verb, Adjective, Adverb, Interjection
	# Forget anything else
	my @pos = qw(Noun Verb Adjective Adverb Interjection);

	my $finaltext = '';
	foreach my $p (@pos)
	{
		my @matches = ( $text =~ /(====?$p====?\n.*?)\n[=]+[^=]+[=]+/gs );
		my $ctr = 1;
		foreach my $m (@matches) {
			# Convert everything to H4
			$m =~ s/[=]+$p[=]+\n/====$p====\n/;
			if ($ctr > 1) {$m =~ s/====($p)====/====$1 (etymology $ctr)====/g;}
			$finaltext .= "$m\n";
			$ctr++;
		}
	}

	#print "$finaltext\n";

	# Convert to HTML
	my $html = wiki2html($finaltext);
	# Change the links
	# <a href='classical%20Hollywood%20cinema'>classical Hollywood cinema</a>
	$html =~ s/<a href='([^']+)'>/"<a href='" . ToLink($1) . "'>"/eg;

	# Replace \x{NUM} with &#NUM;
	$html =~ s/([^[:ascii:]])/'&#'.ord($1).';'/ge;

	return $html;
}

sub ToLink
{
	my $w = shift;
	# Remove HTML entities
	$w =~ s/\%([0-9a-f]{2})/chr(hex($1))/egi;
	# Remove trailing parentheses
	$w =~ s/\s*\([^\)]+\)\s*$//;
	return ToXword($w);
}

sub ToXword
{
	my $w = shift;
	# Capitalize and remove non-alphanumerics
	$w = uc($w);
	$w =~ s/[^A-Z0-9]//g;
	return $w;
}

sub normalize
{
        my $w = shift;
        my %rep = (
        chr(226).chr(128).chr(156) => '"',
        chr(226).chr(128).chr(157) => '"',
        chr(226).chr(128).chr(153) => "'",
        chr(226).chr(128).chr(152) => "'",
        chr(226).chr(128).chr(148) => '___',
        chr(226).chr(128).chr(147) => '--',
        chr(226).chr(128).chr(148) => '---',
        chr(226).chr(128).chr(162) => '*',
        chr(194).chr(183) => '*',
        chr(226).chr(128).chr(166) => '...',
        chr(8217) => "'",
        chr(8216) => "'",
        chr(8220) => '"',
        chr(8221) => '"',
        chr(8230) => '...',
        );
        #while (my ($k,$v) = each (%rep))
        #{
        #	$w =~ s/$k/$v/ge;
        #}
        # Remove any remaining non-ASCII characters
        #$w =~ s/([^[:ascii:]])/'&#'.ord($1).';'/ge;
        return $w;
}
