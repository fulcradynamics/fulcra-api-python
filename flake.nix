{
  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs?ref=nixpkgs-unstable";
    flake-utils.url = "github:numtide/flake-utils";

    pyproject-nix = {
      url = "github:pyproject-nix/pyproject.nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
    uv2nix = {
      url = "github:pyproject-nix/uv2nix";
      inputs.pyproject-nix.follows = "pyproject-nix";
      inputs.nixpkgs.follows = "nixpkgs";
    };
  };
  outputs =
    {
      self,
      nixpkgs,
      flake-utils,
      pyproject-nix,
      uv2nix,
    }:
    let
      # Build the package and its dependencies from uv.lock, preferring
      # binary wheels so pandas/pyarrow/numpy don't compile from source.
      workspace = uv2nix.lib.workspace.loadWorkspace { workspaceRoot = ./.; };
      overlay = workspace.mkPyprojectOverlay { sourcePreference = "wheel"; };
    in
    flake-utils.lib.eachDefaultSystem (
      system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
        python = pkgs.python313;

        pythonSet =
          (pkgs.callPackage pyproject-nix.build.packages { inherit python; }).overrideScope
            (
              nixpkgs.lib.composeManyExtensions [
                overlay
                # fulcra-api's build backend (uv_build), taken from nixpkgs.
                (final: prev: {
                  uv-build = (pkgs.callPackage pyproject-nix.build.hacks { }).nixpkgsPrebuilt {
                    from = python.pkgs.uv-build;
                  };
                })
              ]
            );

        venv = pythonSet.mkVirtualEnv "fulcra-api-env" { fulcra-api = [ ]; };

        fulcra-cli = pkgs.runCommand "fulcra-api-${pythonSet.fulcra-api.version}" {
          meta.mainProgram = "fulcra";
        } ''
          mkdir -p $out/bin
          ln -s ${venv}/bin/fulcra $out/bin/fulcra
        '';
      in
      {
        packages = {
          inherit fulcra-cli venv;
          default = fulcra-cli;
        };

        devShells.default = import ./shell.nix { inherit pkgs; };
      }
    );
}
