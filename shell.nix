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
  env = {
    UV_PYTHON = pythonEnv.python.interpreter;
    UV_PYTHON_DOWNLOADS = "never";
  };
  shellHook = ''
    export PATH=.venv/bin/:$PATH

    # LD_LIBRARY_PATH magic for NixOS + nix-ld environments so we can import numpy/etc
    [ -n "''${NIX_LD_LIBRARY_PATH:-}" ] && export LD_LIBRARY_PATH="$NIX_LD_LIBRARY_PATH" || true
  '';
}
