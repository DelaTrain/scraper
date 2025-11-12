{
  pkgs ? import <nixpkgs> { },
  ...
}:
pkgs.mkShell {
  packages = [
    (pkgs.python313.withPackages (
      ps: with ps; [
        pip
      ]
    ))
  ];
  shellHook = ''
    if [ ! -d ".venv" ]; then
      python -m venv .venv
      source .venv/bin/activate
      pip install .
    else
      source .venv/bin/activate
    fi
  '';
}
