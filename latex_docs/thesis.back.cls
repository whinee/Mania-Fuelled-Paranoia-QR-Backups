% DO NOT CHANGE THIS CODE UNLESS YOU KNOW WHAT YOU'RE DOING!
%-------------------------- identification ---------------------}
\ProvidesClass{thesis}[2024/11/06 v1.2.1 Guide Thesis class]
% Class Produced by George H. Allison to be more inline with LaTeX3 and work with subfiles.
%-------------------------- initial code -----------------------
\DeclareOption*{\PassOptionsToClass{\CurrentOption}{report}}
\ProcessOptions\relax
\LoadClass[a4paper,twoside,openright]{report}
% As an alternative to the above could use next line for twosided output
%\LoadClass[a4paper,twoside,openright]{report}

\RequirePackage{graphicx} % needed for latest frontpage logo
\RequirePackage{tikz}
\RequirePackage{expl3}
\RequirePackage{xparse}

\raggedbottom

%define the default submitted text
\newcommand{\submittedtext}{{A thesis submitted in partial fulfilment of the requirements for the degree of}}

%
% DECLARATIONS
%
% These macros are used to declare arguments needed for the
% construction of the title page and other preamble.

\def\subtitle#1{\gdef\@subtitle{#1}}

% The year and term the thesis is submitted 
\def\degreedate#1{\gdef\@degreedate{#1}}
% The full (unabbreviated) name of the degree
\def\award#1{\gdef\@award{#1}}

\def\faculty#1{\gdef\@faculty{#1}}

\def\school#1{\gdef\@school{#1}}

\def\uniname#1{\gdef\@uniname{#1}}


\ExplSyntaxOn
\NewDocumentCommand{\super}{m}
 {
  \seq_set_split:Nnn \l_tmpa_seq { , } { #1 }
  \int_compare:nNnTF { \seq_count:N \l_tmpa_seq } = { 1 }
   { \gdef\@super{Supervisor:} }
   { \gdef\@super{Supervisors:} }
   \seq_map_inline:Nn \l_tmpa_seq { \tl_put_right:Nx \l_tmpb_tl { ##1 \par } }
  \gdef\@supervisors{\centering \l_tmpb_tl}
 }

%
% Setup choosen crest/logo
%


% Declare and initialize custom logos token list
\tl_new:N \l_customlogos_tl
\tl_clear:N \l_customlogos_tl

% Define a default logo
\NewDocumentCommand{\defaultlogo}{}{
  \includegraphics[width=84mm]{logo.pdf}
}

% Define a command to use the default logo or custom logos if provided
\NewDocumentCommand{\logo}{}{
  \tl_if_empty:NTF \l_customlogos_tl
    {\defaultlogo}
    {\l_customlogos_tl}
}

% Allow users to set custom logos in the main document
\NewDocumentCommand{\setcustomlogo}{m}{
  \tl_set:Nn \l_tmpa_tl {#1}
  \tl_if_in:NnTF \l_tmpa_tl {,}
    {
        % Multiple logos
        \tl_set:Nn \l_customlogos_tl {
            \hbox to \textwidth{
            \seq_set_split:Nnn \l_tmpb_seq {,} {#1}
            \int_zero:N \l_tmpa_int
            \seq_map_inline:Nn \l_tmpb_seq {
                \int_incr:N \l_tmpa_int
                \includegraphics[height=20mm]{##1}
                \int_compare:nNnF {\l_tmpa_int} = {\seq_count:N \l_tmpb_seq}
                {\hfill}
            }
            }
        }
    }
    {
        % Single logo
        \tl_set:Nn \l_customlogos_tl {
            \includegraphics[width=84mm]{#1}
      }
    }
}

% Declare variables
\fp_new:N \l_max_fontsize_fp
\fp_new:N \l_min_fontsize_fp
\fp_new:N \l_scale_factor_fp
\fp_new:N \l_new_fontsize_fp
\dim_new:N \l_target_height_dim
\dim_new:N \l_tmpc_dim
\box_new:N \l_tmpc_box
\tl_new:N \l_tmpc_tl

\cs_new_protected:Nn \adjust_title_size: {
    % Initialize variables with more conservative values
    \fp_set:Nn \l_max_fontsize_fp { 30.0 }
    \fp_set:Nn \l_min_fontsize_fp { 14.0 }
    \dim_set:Nn \l_target_height_dim { 0.1\textheight } % Reduced target height

    \tl_set:Nx \l_tmpc_tl { \@title }

    % Create test box with vbox for better height measurement
    \vbox_set:Nn \l_tmpc_box {
        \centering
        \fontsize{\fp_to_decimal:N \l_max_fontsize_fp}{1.2\fp_to_decimal:N \l_max_fontsize_fp}\selectfont
        \bfseries 
        \parbox{\textwidth}{\centering\l_tmpc_tl}
    }

    % Measure total height
    \dim_set:Nn \l_tmpc_dim { \box_ht:N \l_tmpc_box + \box_dp:N \l_tmpc_box }

    % Calculate scaling with improved precision
    \dim_compare:nNnTF { \l_tmpc_dim } > { \l_target_height_dim }
        {
        \fp_set:Nn \l_scale_factor_fp { 
            \dim_to_fp:n { \l_target_height_dim } / \dim_to_fp:n { \l_tmpc_dim }
        }
        \fp_set:Nn \l_new_fontsize_fp { 
            \fp_max:nn { \l_min_fontsize_fp } { \l_max_fontsize_fp * \l_scale_factor_fp }
        }
        \tl_set:Nn \@titleformat {
            \fontsize{\fp_to_decimal:N \l_new_fontsize_fp}{\fp_eval:n{1.2*\fp_to_decimal:N \l_new_fontsize_fp}pt}\selectfont
            \bfseries
        }
        }
        {
        \tl_set:Nn \@titleformat {
            \fontsize{\fp_to_decimal:N \l_max_fontsize_fp}{\fp_eval:n{1.2*\fp_to_decimal:N \l_max_fontsize_fp}pt}\selectfont
            \bfseries
            \linespread{1.4}
        }
        }
}



%
% Define text area of page and margin offsets
%
\setlength{\topmargin}{0.0in}
\setlength{\oddsidemargin}{0.5in}
\setlength{\evensidemargin}{0in}
\setlength{\textheight}{9.0in}
\setlength{\textwidth}{6.0in}

%
% Environments
%

% This macro define an environment for front matter that is always 
% single column even in a double-column document.

\newenvironment{alwayssingle}{%
        \@restonecolfalse
        \if@twocolumn\@restonecoltrue\onecolumn
        \else\if@openright\cleardoublepage\else\clearpage\fi
        \fi}%
        {\if@restonecol\twocolumn\fi
        \newpage\thispagestyle{empty}}

%define title page layout
\renewcommand{\maketitle}{%
\begin{alwayssingle}
        \adjust_title_size:
        \renewcommand{\footnotesize}{\small}
        \renewcommand{\footnoterule}{\relax}
        \thispagestyle{empty}
    \begin{center}
        {\large {\logo \par}}
        \vspace*{10mm} % Minimum space after logo
        \vfill
        {{\@titleformat
            \parbox{\textwidth}{
                \centering
                \setlength{\baselineskip}{1ex}
                \@title
                \par
                \vspace{0.25em}
                {\large\selectfont\@subtitle}
            }
            } \par}
        \vfill
        \vspace*{5mm} % Minimum space after logo
        {{\Large \@author} \par \vspace*{5mm}}
        {{\large \@super} \par {\large \@supervisors} \par \vspace*{10mm}}
        {{\submittedtext} \par} \vspace*{1ex}
        {\it {\@award} \par} \vspace*{10mm}	
        {\@uniname \par} \vspace*{1ex}
        {\@faculty \par} \vspace*{1ex}
        {\@school \par}\vspace*{10mm}
        {Submission\space Date \par}\vspace*{1ex}
        {\@degreedate \par}
    \end{center}
\end{alwayssingle}}
\ExplSyntaxOff

% DEDICATION
%
% The dedication environment makes sure the dedication gets its
% own page and is set out in verse format.

\newenvironment{dedication}
{\begin{alwayssingle}
    \thispagestyle{empty}
    \begin{center}
    \vspace*{1.5cm}
    {\LARGE }
    \vspace{0.5cm}\par
    \begin{minipage}{0.8\textwidth}
    \centering
    \normalfont\itshape
}
{\end{minipage}\end{center}\end{alwayssingle}}


% ACKNOWLEDGEMENTS
%
% The acknowledgements environment puts a large, bold, centered 
% "Acknowledgements" label at the top of the page. The acknowledgements
% themselves appear in a quote environment, i.e. tabbed in at both sides, and
% on its own page.

\newenvironment{acknowledgements}
{\begin{alwayssingle} \thispagestyle{empty}
\begin{center}
\vspace*{1.5cm}
{\Large \bfseries Acknowledgements}
\end{center}
\vspace{0.5cm}
\begin{quote}}
{\end{quote}\end{alwayssingle}}

% The acknowledgementslong environment puts a large, bold, centered 
% "Acknowledgements" label at the top of the page. The acknowledgement itself 
% does not appears in a quote environment so you can get more in.

\newenvironment{acknowledgementslong}
{\begin{alwayssingle} \thispagestyle{empty}
\begin{center}
\vspace*{1.5cm}
{\Large \bfseries Acknowledgements}
\end{center}
\vspace{0.5cm}}
{\end{alwayssingle}}

% STATEMENT OF ORIGINALITY (AS SUGGESTED BY GSW)
%
% The originality environment puts a large, bold, centered 
% "Statement of originality" label at the top of the page. The statement 
% of originality itself appears in a quote environment, i.e. tabbed in at 
% both sides, and on its own page.

\newenvironment{originality}
{\begin{alwayssingle} \thispagestyle{empty}
\begin{center}
\vspace*{1.5cm}
{\Large \bfseries Statement of Originality}
\end{center}
\vspace{0.5cm}
\begin{quote}}
{\end{quote}\end{alwayssingle}}

% The originalitylong environment puts a large, bold, centered 
% "Statement of originality" label at the top of the page. The statement 
% of originality itself does not appears in a quote environment so you can 
% get more in.

\newenvironment{originalitylong}
{\begin{alwayssingle} \thispagestyle{empty}
\begin{center}
\vspace*{1.5cm}
{\Large \bfseries Statement of Originality}
\end{center}
\vspace{0.5cm}}
{\end{alwayssingle}}


%ABSTRACT
%
%The abstract environment puts a large, bold, centered "Abstract" label at
%the top of the page. The abstract itself appears in a quote environment,
%i.e. tabbed in at both sides, and on its own page.

\renewenvironment{abstract} {\begin{alwayssingle} \thispagestyle{empty}
    \begin{center}
    \vspace*{1.5cm}
    {\Large \bfseries  Abstract}
    \end{center}
    \vspace{0.5cm}
    \begin{quote}}
{\end{quote}\end{alwayssingle}}

%The abstractlong environment puts a large, bold, centered "Abstract" label at
%the top of the page. The abstract itself does not appears in a quote
%environment so you can get more in.

\newenvironment{abstractlong} {\begin{alwayssingle} \thispagestyle{empty}
    \begin{center}
    \vspace*{1.5cm}
    {\Large \bfseries  Abstract}
    \end{center}
    \vspace{0.5cm}}
{\end{alwayssingle}}

%The abstractseparate environment is for running of a page with the abstract
%on including title and author etc as required to be handed in separately

\newenvironment{abstractseparate} {\begin{alwayssingle} \thispagestyle{empty}
    \vspace*{-1in}
    \begin{center}
    { \Large {\bfseries {\@title}} \par}
    {{\large \vspace*{1ex} \@author} \par}
{\large \vspace*{1ex}
    {{\@schoolname} \par}
    {The University of Sheffield \par}
\vspace*{1ex}
    {{\it \submittedtext} \par}
    {\it {\@award} \par}
\vspace*{2ex}
    {\@degreedate}}
    \end{center}}
{\end{alwayssingle}}


%ROMANPAGES
%
% The romanpages environment set the page numbering to lowercase roman one
% for the contents and figures lists. It also resets
% page-numbering for the remainder of the dissertation (arabic, starting at 1).

\newenvironment{romanpages}
{\cleardoublepage\setcounter{page}{1}\renewcommand{\thepage}{\roman{page}}}
{\cleardoublepage\renewcommand{\thepage}{\arabic{page}}\setcounter{page}{1}}
