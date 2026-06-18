"""
hooks/rthook_fix_stderr.py
PyInstaller 运行时钩子：修复 cffi/pycparser 在 console=False 冻结环境中初始化失败。

根因: pycparser.CParser() → yacc.yacc(module=self) 在冻结环境中无法构建语法表
修复: 补丁 CParser.__init__，冻结环境直接从预生成表(yacctab)构建 LRParser
"""
import sys
import os
import io
import types


def _ensure_stderr():
    for attr in ('stderr', 'stdout'):
        if getattr(sys, attr, None) is None:
            try:
                setattr(sys, attr, open(os.devnull, "w", encoding="utf-8"))
            except Exception:
                setattr(sys, attr, io.StringIO())


def _patch_cparser_for_frozen():
    if not getattr(sys, 'frozen', False):
        return
    try:
        import pycparser.c_parser
        import pycparser.c_lexer
        import pycparser.ply.yacc as yacc_mod
    except ImportError:
        return

    _original_init = pycparser.c_parser.CParser.__init__
    _cached_parser = [None]

    def _patched_init(self, *args, **kwargs):
        if _cached_parser[0] is not None:
            self.cparser = _cached_parser[0]
            return

        try:
            _original_init(self, *args, **kwargs)
            _cached_parser[0] = self.cparser
            return
        except Exception:
            pass

        try:
            lr = yacc_mod.LRTable()
            lr.read_table('pycparser.yacctab')

            cls = pycparser.c_parser.CParser
            pdict = {}
            for name, val in vars(cls).items():
                if isinstance(val, types.FunctionType):
                    pdict[name] = types.MethodType(val, self)
                else:
                    pdict[name] = val

            pdict['tokens'] = list(pycparser.c_lexer.CLexer.tokens)
            pdict['start'] = 'translation_unit_or_empty'
            pdict['__module__'] = pycparser.c_parser.__name__
            pdict['__file__'] = pycparser.c_parser.__file__

            if 'p_error' in pdict:
                pdict['error_func'] = pdict['p_error']
            else:
                pdict['error_func'] = lambda p: None

            lr.bind_callables(pdict)
            self.cparser = yacc_mod.LRParser(lr, pdict.get('error_func'))
            _cached_parser[0] = self.cparser
        except Exception:
            try:
                _original_init(self, *args, **kwargs)
                _cached_parser[0] = self.cparser
            except Exception:
                pass

    pycparser.c_parser.CParser.__init__ = _patched_init


_ensure_stderr()
_patch_cparser_for_frozen()
