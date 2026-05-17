"""Python version of the repository config.json

This module provides a CONFIG dictionary equivalent to the
original JSON, converted so it can be imported directly from
Python code.
"""

CONFIG = {
    "compilerOptions": {
        "lib": ["ESNext"],
        "module": "esnext",
        "target": "esnext",
        "moduleResolution": "bundler",
        "moduleDetection": "force",
        "allowImportingTsExtensions": True,
        "noEmit": True,
        "composite": True,
        "strict": True,
        "downlevelIteration": True,
        "skipLibCheck": True,
        "jsx": "react-jsx",
        "allowSyntheticDefaultImports": True,
        "forceConsistentCasingInFileNames": True,
        "allowJs": True,
        "types": [
            "bun-types"  # add Bun global
        ],
    }
}
