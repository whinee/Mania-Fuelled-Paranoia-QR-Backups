# --- Make latexmk rebuild when *any* .tex file changes ---
$dependents_list = 1;

# --- Treat both as main files ---
@default_files = ('latex_docs/1_thesis.tex', 'latex_docs/2_codex.tex');

# --- Optional custom dependency rule (force rebuild on any .tex change) ---
add_cus_dep('tex','pdf',0,'mytex');
sub mytex {
    system("xelatex $_[0]");
}