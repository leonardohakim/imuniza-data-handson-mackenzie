"""Garante que o pacote `src` seja importável ao rodar `pytest` a partir da
raiz do repo, do mesmo jeito que `python -m src.cleaning.clean_pni` já
funciona. Sem isso, dependendo de onde o pytest é chamado, os testes podem
falhar com `ModuleNotFoundError: No module named 'src'`."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
