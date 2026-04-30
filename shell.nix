{
  pkgs ? import <nixpkgs> { },
}:
let
  python = pkgs.python313;
  pythonEnv = python.withPackages (
    pythonPkgs: with pythonPkgs; [
      uv
      pip
      pytest
      ruff
    ]
  );
in
pkgs.mkShell {
  packages = [ pythonEnv ];
  shellHook = ''
    export PYTHONHOME=${pythonEnv}
    export UV_PYTHON_DOWNLOADS=never
    export UV_PYTHON_PREFERENCE=only-system
    export UV_PYTHON=${pythonEnv}
    export PATH=.venv/bin/:$PATH
  '';
}
