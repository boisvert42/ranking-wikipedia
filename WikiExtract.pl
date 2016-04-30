#!/usr/bin/perl -w

use strict;

use Parse::MediaWikiDump;
#use Text::MediawikiFormat as => 'wiki2html';
use Unicode::Normalize;
use Time::Piece;
use Data::Dumper;
use Storable qw (nstore retrieve);
use HTML::Entities;

# I get tons of utf-8 warnings running this.
# The problem appears to be in the get_links subroutine.
# I should probably fix it but I don't know how, so:
no warnings 'utf8';

###########################################################################
# %wiki is a hash where keys are lowercase unaccented Wikipedia page titles.
# Values are:
#	- Original -- the original page title with proper uppercase (no accents, for now)
#	- NumberInLinks -- the number of links to the page
#	- PageLength -- the length of the article
#	- Name -- is 1 if this is a "famous" name
#	- Summary: a summary of the Wikipedia page
###########################################################################
my %wiki;

my $xmlfile = "enwiki-latest-pages-articles.xml";
my $pages = Parse::MediaWikiDump::Pages->new($xmlfile);

# Go through the XML and pull out interesting entries.
my $ctr = 0;
while(defined(my $page = $pages->next))
{
	#main namespace only
	next unless $page->namespace eq '';
	
	# Exclude redirects
	next if defined($page->redirect);
	
	my $t = remove_diacritics($page->title);
	
	# Make sure the title is "interesting"
	next unless is_interesting_title($t);
	
	# Categories
	my $c = $page->categories;
	
	# If we've gotten this far we can proceed
	my $title = $page->title;
	my $rd_title = remove_diacritics($title);
	my $lc_title = lc $rd_title;
	
	$wiki{$lc_title}{'Original'} = $rd_title;
	
	# Get stuff related to the article text
	my $text = $page->text; # This is just a reference
	
	# Get the length of the articles
	my $length = get_length($text);
	
	# HACK: Multiply page length by .8 if
	# it's a city page
	if (grep {/Cities/} @$c) {$length = 0.8 * $length;}
	
	# Determine if it's a name
	if (grep {/^\d+s?( BC)? (births|deaths)$/i} @$c) 
	{
		$wiki{$lc_title}{'Name'} = 1;
	}
	elsif (grep {/^Living people/i} @$c) {$wiki{$lc_title}{'Name'} = 1;}
	else {$wiki{$lc_title}{'Name'} = 0;}
	
	$wiki{$lc_title}{'PageLength'} = $length;
	
	# Get a summary of the page
	
	###print "$title\n";
	#my $summary = get_html_summary($text);
	###my $summary = mw_summary($$text);
	#$wiki{$lc_title}{'Summary'} = $summary;
	#print "\n";
	
	# Update inlinks counter for *other* (linked) articles
	my %links = get_links($text);
	foreach my $ttl (keys %links)
	{
		# Note: this title is already in lowercase and without accents
		$wiki{$ttl}{'NumberInLinks'}++;
	}
	
	# print Dumper($page);
	# die;
	
	#$ctr++;
	#last if $ctr >= 35;
}

# Remove any hash elements that are just inlinks
%wiki = map {$wiki{$_}{'Original'} ? ($_, $wiki{$_}) : ()} keys %wiki;

# Remove anything with no inlinks at all
%wiki = map {$wiki{$_}{'NumberInLinks'} ? ($_, $wiki{$_}) : ()} keys %wiki;

# Hooray!  Send this to a storable so another perl script can process it.
my $t = localtime(time);
my $monYr = $t->strftime("%b%Y");
my $outFile = 'Wiki' . $monYr . '.storable';
nstore \%wiki, $outFile;

#print Dumper(\%wiki);

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
# UPDATE: We now allow pages with parentheses in the title
# We will take out the parentheses in post
# Usage: $goodYN = is_interesting_title($t)
sub is_interesting_title
{
	my $t = shift;
	$t = remove_diacritics($t);
	# 3/8/2012 changed the "good" characters list
	return ( 
	$t =~ /^[A-Za-z0-9\s\!\"\'\*\+\,\-\.\/\:\;\?\\\~\(\)]+$/  # Title contains no "bad" characters
	&& length($t) <= 50  # Title isn't too long
	&& $t !~ /^History/  # These history articles are uninteresting
	&& $t !~ /^List of/  # These are the worst offenders
	&& length(ToXword($t)) >= 3 ); # Title can't be too short
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

# Grab the number of languages the text is translated into.
# This is probably not 100% accurate.
# Usage: $num = get_languages($text)
sub get_languages
{
	my $text = shift;
	$text = $$text;
	$text =~ s/\s//g;
	my $size = 1; $size++ while $text =~ /\[\[[a-z]{2,3}\:.*?\]\]/g;
	return $size;
}

sub get_html_summary
{
	# Get a summary of the article from the text
	# This will just be the first paragraph.
	# We need to remove the junk and make it HTML.
	my ($txt) = @_;
	my $text = $$txt;
	
	# Remove comments and templates (maybe should handle templates..?)
   $text =~ s/\{\{([^\{\}]|(?0))*\}\}//gs;
   $text =~ s/<!--.*?-->//sg;
   # Don't want references..
   $text =~ s/<ref[^\/\>]+\/>//sg;
   $text =~ s/<ref[ >]?.*?<\/ref>//sg;

   my($line, $maybe) = ("", 0);
   for(split /\n/, $text) {
      s/\r//g;
      next if /^\s*$/;

      if(/^\s*(?:[-_#!\t}{:|<=\[]|\W*$)/
        && (!/^\s*\[\[/ || /\[\[Image:/i || /\[\[File:/i)) {
        if($maybe == 1 && /[#!{}|]/) { $maybe = 0; }
        next;
      }

      next if /^\s*\*/ and not $line; # lists in templates, etc.
      next if /^\s*\w+\s*=/; # info boxes..

      if($maybe < 1 && /^(?:the\s+)?'/i) { # '''Thing'' is ....
        $line = "" if $maybe == 0;
        $maybe = 2;
      }

      if($maybe == 1) {
        $maybe++;
      } elsif($maybe == 0) {
        $line = "" if $line;
        $maybe = 1;
      }

      s/\t/ /g;

      if(/\*/ || $maybe == 3) {
        $maybe = 3;
        $line =~ s/,$//, last unless /^\*/;
        if(/^\s*\*+\s*\[\[.*?\]\]\s*-(\s*.*?)\.?\s*$/) {
           $line .= "$1,";
        }else{
           /^\s*\*+\s*(.*?)\.?$/;
           my $st = $1;
           $line .= ($st =~ /[;:,.]$/ ? " $st" : " $st,");
        }
        next;
      }else{
        $line =~ s/\.$/. / if $line;
        $line .= $_;
      }

      next if length($line) < 100;
      last;
   }
	
	$line = wiki2html($line);
	
	if(defined $line) {
      $line =~ s/'''//g;
      $line =~ s/''//g;
      # $line =~ s/{{([^|]+)|(.*?)}}//g;
      # $line =~ s/\[\[(.*?)\]\]/_wp_link($1)/ge;
      # $line =~ s/\[[^ ]+ (.*?)\]/$1/g;
      #$line =~ s/<[^>]+>//g;
      
	  ##I don't think it hurts to remove stuff in parens --ARB
	  $line =~ s/\(([^\(\)]|(?0))*\)//gs;
      ##$line = decode_entities($line);
	  $line =~ s/[ ]+/ /g;
	  $line =~ s/ \,/\,/g;
	  
	  # Remove links
	  $line =~ s/<a [^>]+>//g;
	  $line =~ s/<\/a>//g;
	  # Remove <p> and </p>
	  $line =~ s/<\/p>//g;
	  $line =~ s/<p>//g;
	  
    }
	
	$line =~ s/\s+$//s;
	
	# Truncate to 700 characters
	if (length($line) >= 700)
	{
		$line = substr($line,0,690);
		$line =~ s/\s+[^\s]+$//s;
		$line .= ' ...' unless $line =~ /\.\s*$/s;
	}
	
	return $line;
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

sub mw_summary
{
   my($text) = @_;

   # Remove comments and templates (maybe should handle templates..?)
   $text =~ s/{{.*?}}//sg;
   $text =~ s/<!--.*?-->//sg;
   # Don't want references..
   $text =~ s/<ref[^\/\>]+\/>//sg;
   $text =~ s/<ref[ >]?.*?<\/ref>//sg;

   my($line, $maybe) = ("", 0);
   for(split /\n/, $text) {
      s/\r//g;
      next if /^\s*$/;

      if(/^\s*(?:[-_#!\t}{:|<=\[]|\W*$)/
        && (!/^\s*\[\[/ || /\[\[Image:/i || /\[\[File:/i)) {
        if($maybe == 1 && /[#!{}|]/) { $maybe = 0; }
        next;
      }

      next if /^\s*\*/ and not $line; # lists in templates, etc.
      next if /^\s*\w+\s*=/; # info boxes..

      if($maybe < 1 && /^(?:the\s+)?'/i) { # '''Thing'' is ....
        $line = "" if $maybe == 0;
        $maybe = 2;
      }

      if($maybe == 1) {
        $maybe++;
      } elsif($maybe == 0) {
        $line = "" if $line;
        $maybe = 1;
      }

      s/\t/ /g;

      if(/\*/ || $maybe == 3) {
        $maybe = 3;
        $line =~ s/,$//, last unless /^\*/;
        if(/^\s*\*+\s*\[\[.*?\]\]\s*-(\s*.*?)\.?\s*$/) {
           $line .= "$1,";
        }else{
           /^\s*\*+\s*(.*?)\.?$/;
           my $st = $1;
           $line .= ($st =~ /[;:,.]$/ ? " $st" : " $st,");
        }
        next;
      }else{
        $line =~ s/\.$/. / if $line;
        $line .= $_;
      }

      next if length($line) < 100;
      last;
   }
   
   print "$line\n";

   if(defined $line) {
      $line =~ s/'''//g;
      $line =~ s/''//g;
      $line =~ s/{{([^|]+)|(.*?)}}//g;
      $line =~ s/\[\[(.*?)\]\]/_wp_link($1)/ge;
      $line =~ s/\[[^ ]+ (.*?)\]/$1/g;
	  # I don't think it hurts to remove stuff in parens --ARB
	  $line =~ s/\([^)]+\)//g;
      $line =~ s/<[^>]+>//g;
      $line =~ s/\{\{(.*?)\}\}//g;
      #$line = decode_entities($line);
   }

   if(length($line) > 500) {
      $line = substr($line, 0, 480);
      $line =~ s/ +/ /g;
      if(not($line =~ s/^(.{480}[^\.]+\.).*/$1/)) {
         $line =~ s/^(.{480,}\w+)\W.*/$1/;
      }
      $line =~ s/(?:\.)?\s*$//;
      $line .= "...";
   }

   # fixup places where we've stripped templates
   $line =~ s/\s*,\s*\)/)/g;
   $line =~ s/\(\s*,\s*/(/g;
   $line =~ s/\(\s*\)//g;

   # get rid of extra spacing
   $line =~ s/ +/ /g;
   $line =~ s/(^ | $)//g;

   return $line;
}

sub _wp_link {
  my $link = shift;
  my $x = index($link, '|');
  return substr($link, $x + 1) if $x != -1;
  return $link
}
