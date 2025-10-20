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
      pip install -r requirements.txt
    fi
    source .venv/bin/activate
  '';
}
