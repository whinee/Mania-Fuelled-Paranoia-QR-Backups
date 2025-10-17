\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{base}[2025/10/08 Base class for thesis and documents]

\ProcessOptions\relax
\LoadClass[a4paper,twoside,openleft]{report}

% --- Shared packages ---
\RequirePackage{graphicx}
\RequirePackage{tikz}
\RequirePackage{xparse}
\RequirePackage{expl3}

\raggedbottom

%
% Define text area of page and margin offsets
%
\setlength{\topmargin}{0.0in}
\setlength{\oddsidemargin}{0in}
\setlength{\evensidemargin}{0in}
\setlength{\textheight}{9.0in}
\setlength{\textwidth}{6.0in}

\ExplSyntaxOn
%
% Environments
%

% This macro define an environment for front matter that is always 
% single column even in a double-column document.

\newenvironment{alwayssingle}{%
  \if@twocolumn\onecolumn\fi
  \cleardoublepage\thispagestyle{empty}
}{\newpage}

\ExplSyntaxOff

