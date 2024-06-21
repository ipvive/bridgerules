from distutils.core import setup, Extension
import numpy as np

ext_modules = [ Extension("fastgame", sources = ["fastgame.c"]) ]

setup(
        name = "fastgame",
        version = "1.0",
        include_dirs = [np.get_include()],
        ext_modules = ext_modules
)
