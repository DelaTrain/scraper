{
  pkgs ? import <nixpkgs> { },
  pyproject-nix ?
    import (builtins.fetchGit { url = "https://github.com/pyproject-nix/pyproject.nix.git"; })
      {
        inherit (pkgs) lib;
      },
  ...
}:
let
  python = pkgs.python313;
  project = pyproject-nix.lib.project.loadPyproject { projectRoot = ./.; };
  attrs = project.renderers.withPackages { inherit python; };
in
pkgs.mkShell {
  packages = [ (python.withPackages attrs) ];
}
