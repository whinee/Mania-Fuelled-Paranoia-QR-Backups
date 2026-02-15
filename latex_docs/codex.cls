% DO NOT CHANGE THIS CODE UNLESS YOU KNOW WHAT YOU'RE DOING!
\NeedsTeXFormat{LaTeX2e}
\ProvidesClass{codex}[2025/10/29 v0.1.0 Codex Class]
\LoadClass{base}

\RequirePackage{titlesec}
\RequirePackage{tikz}

\titleformat{\chapter}[display]
  {\normalfont\huge\bfseries\centering}
  {%
    \vspace{-2em}
    \begin{tikzpicture}[baseline=(num.base)]
        \draw[thick] (-0.5\textwidth,0) -- (-1,0);
        \node[
          draw,
          double,
          inner sep=12pt,
          double distance=3pt,
          minimum width=1.2em,
          line width=1pt
        ](num) {\textit{\thechapter}};
        \draw[thick] (1,0) -- (0.5\textwidth,0);
    \end{tikzpicture}
  }
  {-1.5em}
  {\Huge}
  [\vspace{-1em}\rule{\textwidth}{0.4pt}]

\renewcommand{\chaptername}{}
\renewcommand{\thechapter}{\arabic{chapter}}
\titlespacing*{\chapter}{0pt}{*4}{*2}
