#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import sys

# ==================== 词法单元定义 ====================

# 关键字集合
# [设计笔记] 使用 set (集合) 而不是 list (列表) 的原因：
# set 底层基于哈希表实现，查找操作的时间复杂度是 O(1)（常数时间）。
# 如果用 list，查找是 O(n)。在编译过程中我们需要频繁检查一个单词是否是关键字，
# 使用 set 可以显著提高词法分析器的性能，特别是代码量大时。
KEYWORDS = {
    'if', 'then', 'else', 'begin', 'end', 'int', 'float', 'char',
    'while', 'do', 'return', 'for', 'void', 'break', 'continue',
    'switch', 'case', 'default', 'struct', 'const', 'typedef'
}

# 运算符定义 - 按长度分组
# [算法核心] 这里体现了 "最长匹配原则" (Longest Match Principle / Maximal Munch)。
# 比如源代码是 ">>="，我们不应该识别为 ">" + ">=" 或者 ">>" + "="，而应该识别为 ">>="。
# 实现策略：在扫描时，先尝试匹配 TRIPLE_OPS，失败再试 DOUBLE_OPS，最后试 SINGLE_OPS。
SINGLE_OPS = {'+', '-', '*', '/', '%', '=', '&', '|', '^', '~', '!', '<', '>'}
DOUBLE_OPS = {'++', '--', '+=', '-=', '*=', '/=', '%=', '&&', '||',
              '<<', '>>', '&=', '|=', '^=', '<=', '>=', '<>', '==', '!=', '->'}
TRIPLE_OPS = {'<<=', '>>='}

# 界限符
DELIMITERS = {'(', ')', '[', ']', '{', '}', ';', '#', ',', ':', '.'}

# 种别码表 (Token Codes)
# [设计说明] 编译器后端通常需要整数形式的 Token 类型，而不是字符串。
# 这里定义了从 单词字面量 -> 整数编码 的映射。
# 范围规划：
# 1-49:   关键字 (保留字)
# 50-59:  标识符和各种常量 (ID, INT, FLOAT...)
# 60-99:  算术和位运算符
# 100+:   逻辑运算符、比较运算符、界限符等
CODE = {
    # 关键字 (1-25)
    'if': 1, 'then': 2, 'else': 3, 'begin': 4, 'end': 5,
    'int': 6, 'float': 7, 'char': 8, 'while': 9, 'do': 10,
    'return': 11, 'for': 12, 'void': 13, 'break': 14, 'continue': 15,
    'switch': 16, 'case': 17, 'default': 18, 'struct': 19,
    'const': 20, 'typedef': 21,

    # 标识符和常量 (50-56) - 同类共用一个码，靠属性值区分
    'ID': 50, 'INT': 51, 'FLOAT': 52, 'CHAR': 53,
    'STRING': 54, 'HEX': 55, 'OCT': 56,

    # 算术运算符 (60-72)
    '+': 60, '-': 61, '*': 62, '/': 63, '%': 64, '=': 65,
    '++': 66, '--': 67, '+=': 68, '-=': 69, '*=': 70, '/=': 71, '%=': 72,

    # 位运算符 (80-90)
    '&': 80, '|': 81, '^': 82, '~': 83, '<<': 84, '>>': 85,
    '&=': 86, '|=': 87, '^=': 88, '<<=': 89, '>>=': 90,

    # 逻辑运算符 (100-102)
    '&&': 100, '||': 101, '!': 102,

    # 比较运算符 (110-116)
    '<': 110, '>': 111, '<=': 112, '>=': 113, '<>': 114, '==': 115, '!=': 116,

    # 其他
    '->': 120,

    # 界限符 (130-140)
    '(': 130, ')': 131, '[': 132, ']': 133, '{': 134, '}': 135,
    ';': 136, '#': 137, ',': 138, ':': 139, '.': 140,
}

# 转义字符映射表
# [功能说明] 用于将源代码中的转义序列（如字符 'n'）映射为实际的控制字符（如换行符 '\n'）。
# 在处理字符串 "hello\nworld" 时，扫描器读到 '\' 后会查这个表。
ESCAPE_CHARS = {
    'n': '\n', 't': '\t', 'r': '\r', '0': '\0',
    '\\': '\\', "'": "'", '"': '"', 'a': '\a',
    'b': '\b', 'f': '\f', 'v': '\v'
}


class Token:
    """
    Token (词法单元) 类
    表示源代码中被识别出的一个最小语法单位。
    """

    def __init__(self, code, value, attr, line, col):
        self.code = code    # [种别码] 整数，代表这是什么类型的Token (如 1代表if, 50代表标识符)
        self.value = value  # [单词值] 源代码中实际的字符串文本 (如 "count", "123")
        self.attr = attr    # [属性值] 指向符号表/常量表的指针，或者占位符 '-'
                            # - 关键字/运算符: 不需要额外属性，记为 '-'
                            # - 标识符(ID): 记为 'SYM:n'，n是符号表中的索引
                            # - 常量(CONST): 记为 'CONST:n'，n是常量表中的索引
        self.line = line    # [行号] 用于报错定位
        self.col = col      # [列号] 用于报错定位

    def __repr__(self):
        return f"({self.code}, '{self.value}', {self.attr})"


class LexError:
    """
    词法错误类
    用于封装词法分析过程中发现的错误信息。
    """

    ERROR_TYPES = {
        'ILLEGAL_CHAR': '非法字符',
        'ILLEGAL_ID': '非法标识符',
        'ILLEGAL_NUMBER': '非法数字格式',
        'ILLEGAL_HEX': '非法十六进制数',
        'ILLEGAL_OCT': '非法八进制数',
        'ILLEGAL_FLOAT': '非法浮点数格式',
        'UNCLOSED_STRING': '字符串未闭合',
        'UNCLOSED_CHAR': '字符常量未闭合',
        'UNCLOSED_COMMENT': '多行注释未闭合',
        'EMPTY_CHAR': '空字符常量',
        'MULTI_CHAR': '字符常量包含多个字符',
        'ILLEGAL_ESCAPE': '非法转义序列',
        'LEADING_ZERO': '整数不应有前导零',
    }

    def __init__(self, error_type, line, col, value, extra_info=''):
        self.error_type = error_type
        self.msg = self.ERROR_TYPES.get(error_type, error_type)
        self.line = line
        self.col = col
        self.value = value
        self.extra_info = extra_info

    def __repr__(self):
        info = f" ({self.extra_info})" if self.extra_info else ""
        return f"[行{self.line}:列{self.col}] {self.msg}: '{self.value}'{info}"


class Lexer:
    """
    词法分析器 (Lexer / Scanner)
    
    [工作原理]
    这是一个基于 "手写状态机" 的词法分析器。
    它维护一个当前指针 pos，逐个读取字符，根据首字符判断进入哪个分支（状态）。
    例如：读到字母 -> 进入标识符扫描；读到数字 -> 进入数字扫描。
    """

    def __init__(self, source):
        self.src = source          # 源代码字符串
        self.pos = 0               # [指针] 当前扫描到的字符索引
        self.line = 1              # [计数器] 当前行号 (遇到 \n 加 1)
        self.col = 1               # [计数器] 当前列号 (每读一个字符 加 1，换行归 1)
        self.tokens = []           # [输出] 最终生成的 Token 列表
        self.errors = []           # [输出] 发现的词法错误列表
        self.sym_table = []        # [符号表] 存储所有识别出的标识符 (去重)
        self.const_table = []      # [常量表] 存储所有识别出的常量 (去重)

    # ---------- 符号表/常量表操作 ----------

    def _add_sym(self, name):
        """添加标识符到符号表，返回索引"""
        if name not in self.sym_table:
            self.sym_table.append(name)
        return self.sym_table.index(name)

    def _add_const(self, val):
        """添加常量到常量表，返回索引"""
        if val not in self.const_table:
            self.const_table.append(val)
        return self.const_table.index(val)

    # ---------- 字符读取 ----------

    def _char(self):
        """获取当前字符，到末尾返回None"""
        return self.src[self.pos] if self.pos < len(self.src) else None

    def _peek(self, offset=1):
        """
        [辅助函数] 偷看 (Lookahead)
        查看当前位置后面第 offset 个字符，但【不移动】指针 pos。
        用途：用于预判。例如读到 '>' 时，需要偷看下一位是 '=' 还是其他，
             如果是 '=' 则是 '>='，否则只是 '>'。
        """
        idx = self.pos + offset
        return self.src[idx] if idx < len(self.src) else None

    def _advance(self):
        """
        [辅助函数] 前进 (Consume)
        返回当前字符，并将指针 pos 向后移动一位。
        同时负责维护 line (行号) 和 col (列号) 的更新。
        """
        ch = self._char()
        if ch:
            self.pos += 1
            if ch == '\n':
                self.line += 1
                self.col = 1
            else:
                self.col += 1
        return ch

    # ---------- 跳过空白和注释 ----------

    def _skip_ws(self):
        """跳过空白字符"""
        while self._char() in ' \t\r\n':
            self._advance()

    def _skip_comment(self):
        """
        [扫描逻辑] 跳过注释
        支持两种注释风格：
        1. 单行注释 // ... (直到行尾)
        2. 多行注释 /* ... */ (直到遇到 */)
        """
        if self._char() != '/':
            return False

        # 单行注释 //
        if self._peek() == '/':
            while self._char() and self._char() != '\n':
                self._advance()
            return True

        # 多行注释 /* */
        if self._peek() == '*':
            sl, sc = self.line, self.col  # 记录开始位置，用于报错
            self._advance()  # 跳 /
            self._advance()  # 跳 *
            while self._char():
                if self._char() == '*' and self._peek() == '/':
                    self._advance()
                    self._advance()
                    return True
                self._advance()
            # 没找到*/，注释未闭合
            self.errors.append(LexError('UNCLOSED_COMMENT', sl, sc, "/*"))
            return True

        return False

    # ---------- 扫描标识符/关键字 ----------

    def _scan_id(self):
        """
        [扫描逻辑] 标识符 (Identifier) 和 关键字 (Keyword)
        
        逻辑：
        1. 标识符和关键字的组成规则一样（字母/下划线开头，后跟字母/数字/下划线）。
        2. 所以先统一扫描下来，得到一个字符串。
        3. 然后查 KEYWORDS 表：
           - 如果在表中 -> 它是关键字 (如 if, while)
           - 如果不在表中 -> 它是用户定义的标识符 (如 count, main)
        """
        sl, sc = self.line, self.col  # 记录单词开始的位置
        val = ''

        # 循环读取后续的合法字符 (字母、数字、下划线)
        while self._char() and (self._char().isalnum() or self._char() == '_'):
            val += self._advance()

        # 查表区分关键字和标识符
        if val.lower() in KEYWORDS:
            # 是关键字：返回对应的种别码，属性值为 '-'
            return Token(CODE[val.lower()], val, '-', sl, sc)

        # 是标识符：加入符号表，属性值为符号表索引 'SYM:n'
        idx = self._add_sym(val)
        return Token(CODE['ID'], val, f'SYM:{idx}', sl, sc)

    def _scan_illegal_id(self):
        """扫描以数字开头的非法标识符，如1abc"""
        sl, sc = self.line, self.col
        val = ''
        while self._char() and (self._char().isalnum() or self._char() == '_'):
            val += self._advance()
        self.errors.append(LexError('ILLEGAL_ID', sl, sc, val, "标识符不能以数字开头"))
        return None

    # ---------- 扫描数字 ----------

    def _scan_num(self):
        """
        [扫描逻辑] 数字常量 (Number) 入口
        
        逻辑分支：
        1. 如果以 '0' 开头：
           - 后面跟 'x' 或 'X' -> 是十六进制 (Hex)，转交给 _scan_hex
           - 后面跟其他数字 -> 是八进制 (Octal)，转交给 _scan_octal
           - 否则 -> 可能是 0 本身，或者 0.123 (浮点数)，转交给 _scan_decimal
        2. 如果以 1-9 开头 -> 是十进制或浮点数，转交给 _scan_decimal
        """
        sl, sc = self.line, self.col

        # 检查前缀来决定数字类型
        if self._char() == '0':
            if self._peek() in ('x', 'X'):  # 匹配 0x...
                return self._scan_hex(sl, sc)
            elif self._peek() and self._peek().isdigit():  # 匹配 0123...
                return self._scan_octal(sl, sc)

        # 默认按十进制处理 (包含整数和浮点数)
        return self._scan_decimal(sl, sc)

    def _scan_hex(self, sl, sc):
        """扫描十六进制数 0x1F"""
        val = self._advance() + self._advance()  # 读0x
        hex_digits = ''

        while self._char() and (self._char().isdigit() or self._char().lower() in 'abcdef'):
            hex_digits += self._advance()

        if not hex_digits:
            # 0x后面没有合法数字
            if self._char() and self._char().isalpha():
                while self._char() and (self._char().isalnum() or self._char() == '_'):
                    hex_digits += self._advance()
                self.errors.append(LexError('ILLEGAL_HEX', sl, sc, val + hex_digits, "包含非法字符"))
            else:
                self.errors.append(LexError('ILLEGAL_HEX', sl, sc, val, "缺少十六进制数字"))
            return None

        val += hex_digits
        idx = self._add_const(val)
        return Token(CODE['HEX'], val, f'CONST:{idx}', sl, sc)

    def _scan_octal(self, sl, sc):
        """扫描八进制数 07"""
        val = self._advance()  # 读开头的0

        while self._char() and self._char().isdigit():
            if self._char() in '89':  # 八进制不能有8和9
                while self._char() and self._char().isdigit():
                    val += self._advance()
                self.errors.append(LexError('ILLEGAL_OCT', sl, sc, val, "八进制数不能包含8或9"))
                return None
            val += self._advance()

        # 后面跟字母是非法的
        if self._char() and self._char().isalpha():
            while self._char() and (self._char().isalnum() or self._char() == '_'):
                val += self._advance()
            self.errors.append(LexError('ILLEGAL_NUMBER', sl, sc, val))
            return None

        # 可能是0.5这样的浮点数
        if self._char() == '.' and self._peek() and self._peek().isdigit():
            return self._scan_decimal_part(val, sl, sc)

        idx = self._add_const(val)
        return Token(CODE['OCT'], val, f'CONST:{idx}', sl, sc)

    def _scan_decimal(self, sl, sc):
        """扫描十进制整数部分"""
        val = ''
        while self._char() and self._char().isdigit():
            val += self._advance()
        return self._scan_decimal_part(val, sl, sc)

    def _scan_decimal_part(self, int_part, sl, sc):
        """扫描小数部分和指数部分"""
        val = int_part
        has_dot = False
        has_exp = False

        # 小数部分
        if self._char() == '.':
            if self._peek() == '.':  # 是..运算符，不是小数点
                if val:
                    idx = self._add_const(val)
                    return Token(CODE['INT'], val, f'CONST:{idx}', sl, sc)
                return None

            has_dot = True
            val += self._advance()  # 读小数点

            frac_digits = ''
            while self._char() and self._char().isdigit():
                frac_digits += self._advance()

            if not frac_digits and not int_part:
                self.errors.append(LexError('ILLEGAL_FLOAT', sl, sc, val, "缺少数字"))
                return None
            val += frac_digits

            # 不能有两个小数点
            if self._char() == '.':
                extra = ''
                while self._char() and (self._char().isdigit() or self._char() == '.'):
                    extra += self._advance()
                self.errors.append(LexError('ILLEGAL_FLOAT', sl, sc, val + extra, "多个小数点"))
                return None

        # 科学计数法 e/E
        if self._char() and self._char().lower() == 'e':
            has_exp = True
            val += self._advance()

            if self._char() in ('+', '-'):  # 可选的正负号
                val += self._advance()

            exp_digits = ''
            while self._char() and self._char().isdigit():
                exp_digits += self._advance()

            if not exp_digits:
                self.errors.append(LexError('ILLEGAL_FLOAT', sl, sc, val, "指数部分缺少数字"))
                return None
            val += exp_digits

        # 数字后不能直接跟字母
        if self._char() and (self._char().isalpha() or self._char() == '_'):
            extra = ''
            while self._char() and (self._char().isalnum() or self._char() == '_'):
                extra += self._advance()
            self.errors.append(LexError('ILLEGAL_NUMBER', sl, sc, val + extra, "数字后不能直接跟字母"))
            return None

        if not val:
            return None

        idx = self._add_const(val)
        code = CODE['FLOAT'] if (has_dot or has_exp) else CODE['INT']
        return Token(code, val, f'CONST:{idx}', sl, sc)

    def _scan_leading_dot_number(self):
        """扫描.5这样的浮点数"""
        sl, sc = self.line, self.col
        if self._char() == '.' and self._peek() and self._peek().isdigit():
            return self._scan_decimal_part('', sl, sc)
        return None

    # ---------- 扫描字符常量 ----------

    def _scan_char(self):
        """扫描字符常量 'a' '\\n' '\\x41'"""
        sl, sc = self.line, self.col
        self._advance()  # 跳过开头的'

        if self._char() is None or self._char() == '\n':
            self.errors.append(LexError('UNCLOSED_CHAR', sl, sc, "'"))
            return None

        if self._char() == "'":  # 空字符''
            self._advance()
            self.errors.append(LexError('EMPTY_CHAR', sl, sc, "''"))
            return None

        char_val = ''
        display_val = "'"

        if self._char() == '\\':  # 转义字符
            display_val += self._advance()
            if self._char() is None:
                self.errors.append(LexError('UNCLOSED_CHAR', sl, sc, display_val))
                return None

            escape_char = self._char()
            display_val += self._advance()

            if escape_char == 'x':  # 十六进制转义 \x41
                hex_val = ''
                for _ in range(2):
                    if self._char() and self._char().lower() in '0123456789abcdef':
                        hex_val += self._advance()
                        display_val += hex_val[-1]
                if hex_val:
                    char_val = chr(int(hex_val, 16))
                else:
                    self.errors.append(LexError('ILLEGAL_ESCAPE', sl, sc, display_val))
                    while self._char() and self._char() != "'" and self._char() != '\n':
                        self._advance()
                    if self._char() == "'":
                        self._advance()
                    return None
            elif escape_char in ESCAPE_CHARS:
                char_val = ESCAPE_CHARS[escape_char]
            elif escape_char.isdigit():  # 八进制转义 \101
                oct_val = escape_char
                for _ in range(2):
                    if self._char() and self._char().isdigit() and self._char() < '8':
                        oct_val += self._advance()
                        display_val += oct_val[-1]
                char_val = chr(int(oct_val, 8))
            else:
                self.errors.append(LexError('ILLEGAL_ESCAPE', sl, sc, f"\\{escape_char}"))
                char_val = escape_char
        else:  # 普通字符
            char_val = self._char()
            display_val += self._advance()

        # 检查多余字符
        extra_chars = ''
        while self._char() and self._char() != "'" and self._char() != '\n':
            extra_chars += self._advance()
            display_val += extra_chars[-1]

        if self._char() != "'":
            self.errors.append(LexError('UNCLOSED_CHAR', sl, sc, display_val))
            return None

        display_val += self._advance()  # 读闭合的'

        if extra_chars:
            self.errors.append(LexError('MULTI_CHAR', sl, sc, display_val))
            return None

        idx = self._add_const(display_val)
        return Token(CODE['CHAR'], display_val, f'CONST:{idx}', sl, sc)

    # ---------- 扫描字符串常量 ----------

    def _scan_string(self):
        """扫描字符串常量 "hello" """
        sl, sc = self.line, self.col
        self._advance()  # 跳过开头的"

        val = '"'
        string_content = ''

        while self._char() and self._char() != '"' and self._char() != '\n':
            if self._char() == '\\':  # 转义
                val += self._advance()
                if self._char() is None or self._char() == '\n':
                    break

                escape_char = self._char()
                val += self._advance()

                if escape_char == 'x':
                    hex_val = ''
                    for _ in range(2):
                        if self._char() and self._char().lower() in '0123456789abcdef':
                            c = self._advance()
                            hex_val += c
                            val += c
                    if hex_val:
                        string_content += chr(int(hex_val, 16))
                    else:
                        self.errors.append(LexError('ILLEGAL_ESCAPE', sl, sc, "\\x"))
                elif escape_char in ESCAPE_CHARS:
                    string_content += ESCAPE_CHARS[escape_char]
                elif escape_char.isdigit():
                    oct_val = escape_char
                    for _ in range(2):
                        if self._char() and self._char().isdigit() and self._char() < '8':
                            c = self._advance()
                            oct_val += c
                            val += c
                    string_content += chr(int(oct_val, 8))
                else:
                    self.errors.append(LexError('ILLEGAL_ESCAPE', sl, sc, f"\\{escape_char}"))
                    string_content += escape_char
            else:
                string_content += self._char()
                val += self._advance()

        if self._char() != '"':
            self.errors.append(LexError('UNCLOSED_STRING', sl, sc, val))
            return None

        val += self._advance()
        idx = self._add_const(val)
        return Token(CODE['STRING'], val, f'CONST:{idx}', sl, sc)

    # ---------- 扫描运算符 ----------

    def _scan_op(self):
        """
        [扫描逻辑] 运算符 (Operator)
        
        核心算法：最长匹配原则 (Maximal Munch)
        我们必须尽可能多地匹配字符，以避免歧义。
        
        例子：对于序列 ">>="
        1. 尝试匹配 3 个字符 ">>=" -> 成功！返回 ">>=" Token。
        2. 如果失败，尝试匹配 2 个字符 ">>" -> 成功！返回 ">>" Token。
        3. 如果失败，匹配 1 个字符 ">" -> 返回 ">" Token。
        """
        sl, sc = self.line, self.col
        ch = self._char()

        # 1. 尝试匹配三字符运算符 (如 <<=)
        if self._peek() and self._peek(2):
            three = ch + self._peek() + self._peek(2)
            if three in TRIPLE_OPS:
                self._advance() # 吃掉第1个
                self._advance() # 吃掉第2个
                self._advance() # 吃掉第3个
                return Token(CODE[three], three, '-', sl, sc)

        # 2. 尝试匹配双字符运算符 (如 ++, >=)
        if self._peek():
            two = ch + self._peek()
            if two in DOUBLE_OPS:
                self._advance() # 吃掉第1个
                self._advance() # 吃掉第2个
                return Token(CODE[two], two, '-', sl, sc)

        # 3. 匹配单字符运算符 (如 +, -)
        if ch in SINGLE_OPS:
            self._advance() # 吃掉它
            return Token(CODE[ch], ch, '-', sl, sc)

        return None

    # ---------- 扫描界限符 ----------

    def _scan_delim(self):
        """扫描界限符"""
        sl, sc = self.line, self.col
        ch = self._char()
        if ch in DELIMITERS:
            self._advance()
            return Token(CODE[ch], ch, '-', sl, sc)
        return None

    # ---------- 主循环 ----------

    def tokenize(self):
        """
        [主循环] 词法分析主控函数 (Driver Loop)
        
        流程：
        1. 跳过空白字符 (空格、Tab、换行)。
        2. 尝试跳过注释 (// 或 /* ... */)。
        3. 如果还有字符，读取当前首字符 (Lookahead char)。
        4. [分派逻辑] 根据首字符的类型，决定调用哪个扫描子程序：
           - 字母/_ -> _scan_id (标识符/关键字)
           - 数字   -> _scan_num (数字常量)
           - 单引号 -> _scan_char (字符常量)
           - 双引号 -> _scan_string (字符串常量)
           - 运算符 -> _scan_op
           - 界限符 -> _scan_delim
        5. 循环直到文件结束。
        """
        while self.pos < len(self.src):
            self._skip_ws()  # 步骤1: 过滤空白
            if not self._char():
                break
            if self._skip_comment():  # 步骤2: 过滤注释
                continue

            ch = self._char()
            sl, sc = self.line, self.col

            # 步骤4: 分派 (Dispatch)
            if ch.isalpha() or ch == '_':  # 以字母或下划线开头 -> 标识符或关键字
                self.tokens.append(self._scan_id())

            elif ch.isdigit():  # 以数字开头 -> 数字常量
                # [错误处理预判] 检查是否是 "123abc" 这种非法标识符
                temp_pos = self.pos
                while temp_pos < len(self.src) and (self.src[temp_pos].isalnum() or self.src[temp_pos] == '_'):
                    temp_pos += 1
                temp_val = self.src[self.pos:temp_pos]
                has_letter = any(c.isalpha() for c in temp_val)
                is_hex = temp_val.lower().startswith('0x')
                is_exp = 'e' in temp_val.lower() and not any(c.isalpha() and c.lower() not in 'abcdefx' for c in temp_val)
                if has_letter and not is_hex and not is_exp:
                    pass # 这里其实可以优化，但为了保持逻辑简单，交给 _scan_num 内部去报错
                tok = self._scan_num()
                if tok:
                    self.tokens.append(tok)

            elif ch == '.' and self._peek() and self._peek().isdigit():  # 以点开头且后面是数字 -> 浮点数 (.5)
                tok = self._scan_leading_dot_number()
                if tok:
                    self.tokens.append(tok)

            elif ch == "'":  # 单引号 -> 字符常量
                tok = self._scan_char()
                if tok:
                    self.tokens.append(tok)

            elif ch == '"':  # 双引号 -> 字符串常量
                tok = self._scan_string()
                if tok:
                    self.tokens.append(tok)

            elif ch in SINGLE_OPS or (ch + (self._peek() or '')) in DOUBLE_OPS:  # 运算符
                if ch == '/' and self._peek() in ('/', '*'):  # 注释 (虽然前面处理过，这里是双重保险)
                    continue
                tok = self._scan_op()
                if tok:
                    self.tokens.append(tok)

            elif ch in DELIMITERS:  # 界限符
                tok = self._scan_delim()
                if tok:
                    self.tokens.append(tok)
                if ch == '#':  # 约定 # 为程序结束符
                    break

            else:  # 无法识别的字符 -> 报错并跳过
                self.errors.append(LexError('ILLEGAL_CHAR', sl, sc, ch))
                self._advance()

        return self.tokens, self.errors

    # ---------- 输出结果 ----------

    def print_result(self):
        """打印分析结果"""
        print("\n" + "=" * 75)
        print("词法分析结果")
        print("=" * 75)
        print(f"\n{'序号':<5}{'种别码':<8}{'单词':<15}{'属性值':<15}{'位置'}")
        print("-" * 75)

        for i, t in enumerate(self.tokens, 1):
            val_display = t.value[:12] + '...' if len(t.value) > 15 else t.value
            print(f"{i:<5}{t.code:<8}{val_display:<15}{t.attr:<15}({t.line},{t.col})")

        print("\n" + "-" * 75)
        print("标识符表:", self.sym_table if self.sym_table else "(空)")
        print("常量表:  ", self.const_table if self.const_table else "(空)")

        if self.errors:
            print("\n" + "=" * 75)
            print(f"发现 {len(self.errors)} 个错误:")
            print("-" * 75)
            for e in self.errors:
                print(f"  {e}")
        print("=" * 75)

    def save_result(self, path):
        """保存结果到文件"""
        with open(path, 'w', encoding='utf-8') as f:
            f.write("=" * 60 + "\n")
            f.write("词法分析结果\n")
            f.write("=" * 60 + "\n\n")
            f.write("Token序列\n")
            f.write("-" * 60 + "\n")
            for i, t in enumerate(self.tokens, 1):
                f.write(f"{i:3}. {t}\n")
            f.write(f"\n标识符表: {self.sym_table}\n")
            f.write(f"常量表:   {self.const_table}\n")
            if self.errors:
                f.write("\n" + "=" * 60 + "\n")
                f.write(f"错误列表 ({len(self.errors)} 个):\n")
                f.write("-" * 60 + "\n")
                for e in self.errors:
                    f.write(f"  {e}\n")


def main():
    """主函数"""
    input_file = sys.argv[1] if len(sys.argv) > 1 else "input.txt"

    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            source = f.read()
    except FileNotFoundError:
        print(f"找不到文件: {input_file}")
        return 1

    print(f"输入文件: {input_file}")
    print("-" * 60)
    print(source)
    print("-" * 60)

    lexer = Lexer(source)
    lexer.tokenize()
    lexer.print_result()
    lexer.save_result("output.txt")
    print(f"\n结果已保存到 output.txt")

    if lexer.errors:
        print(f"\n警告: 发现 {len(lexer.errors)} 个词法错误")
        return 1

    print("\n词法分析完成!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
