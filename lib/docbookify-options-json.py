# Reads a raw options.xml file from standard input, converts any Markdown values
# into DocBook markup, and writes back the resulting XML to standard output.

import collections
import json
import mistune  # for MD conversion
import re
import sys
from asciidoc.api import AsciiDocAPI
from enum import Enum
from io import StringIO
from typing import Any, Dict, List
from xml.sax.saxutils import escape, quoteattr
from mistune.renderers.markdown import MarkdownRenderer

JSON = Dict[str, Any]


class Key:

    def __init__(self, path: List[str]):
        self.path = path

    def __hash__(self):
        result = 0
        for id in self.path:
            result ^= hash(id)
        return result

    def __eq__(self, other):
        return type(self) is type(other) and self.path == other.path


# pivot a dict of options keyed by their display name to a dict keyed by their path
def pivot(options: List[JSON]) -> Dict[Key, JSON]:
    result: Dict[Key, JSON] = dict()
    for opt in options:
        result[Key(opt['loc'])] = opt
    return result


# pivot back to indexed-by-full-name
# like the docbook build we'll just fail if multiple options with differing locs
# render to the same option name.
def unpivot(options: Dict[Key, JSON]) -> List[JSON]:
    result: Dict[str, Dict] = dict()
    for opt in options.values():
        name = opt['name']
        if name in result:
            raise RuntimeError(
                'multiple options with colliding ids found',
                name,
                result[name]['loc'],
                opt['loc'],
            )
        result[name] = opt
    return list(result.values())


admonitions = {
    '.warning': 'warning',
    '.important': 'important',
    '.note': 'note'
}

# Allowed child elements for the DocBook listitem element. See
# https://tdg.docbook.org/tdg/5.1/listitem.html
ALLOWED_LISTITEM_CHILD = re.compile(
    '<(?:address|anchor|annotation|bibliolist|blockquote|bridgehead|calloutlist|caution|classsynopsis|cmdsynopsis|constraintdef|constructorsynopsis|destructorsynopsis|epigraph|equation|example|fieldsynopsis|figure|formalpara|funcsynopsis|glosslist|important|indexterm|indexterm|indexterm|informalequation|informalexample|informalfigure|informaltable|informaltable|itemizedlist|literallayout|mediaobject|methodsynopsis|msgset|note|orderedlist|para|procedure|productionset|programlisting|programlistingco|qandaset|remark|revhistory|screen|screenco|screenshot|segmentedlist|sidebar|simpara|simplelist|synopsis|table|table|task|tip|variablelist|warning)[> ]'
)


class Renderer(MarkdownRenderer):

    def _get_method(self, name):
        try:
            return super(Renderer, self)._get_method(name)
        except AttributeError:

            def not_supported(*args, **kwargs):
                raise NotImplementedError("md node not supported yet", name,
                                          args, **kwargs)

            return not_supported

    def render_children(self, token, state):
        return self.render_tokens(token['children'], state)

    def text(self, token, state):
        return escape(token['raw'])

    def paragraph(self, token, state):
        return f"<simpara>{self.render_children(token, state)}</simpara>\n"

    # def blank_line(self, token, state):
    #     return ""

    def newline(self, token, state):
        return "<literallayout>\n</literallayout>"

    def codespan(self, token, state):
        text = token['raw']
        return f"<literal>{escape(text)}</literal>"

    def block_code(self, token, info=None):
        attrs = token.get('attrs', {})
        info = attrs.get('info', '')
        code = token['raw']

        info = f" language={quoteattr(info)}"
        return f"<programlisting{info}>\n{escape(code)}</programlisting>"

    def link(self, token, state):
        # TODO: I maybe should render text
        text = self.render_children(token, state)
        link = token['attrs']['url']
        tag = "link"
        if link[0:1] == '#':
            if text == "":
                tag = "xref"
            attr = "linkend"
            link = quoteattr(link[1:])
        else:
            # try to faithfully reproduce links that were of the form <link href="..."/>
            # in docbook format
            if text == link:
                text = ""
            attr = "xlink:href"
            link = quoteattr(link)
        return f"<{tag} {attr}={link}>{text}</{tag}>"

    def list(self, token, state):
        text = self.render_children(token, state)
        attrs = token['attrs']
        if attrs['ordered']:
            raise NotImplementedError("ordered lists not supported yet")
        return f"<itemizedlist>\n{text}\n</itemizedlist>"

    def list_item(self, token, state):
        text = self.render_children(token, state)

        # If the list item does not contain an allowed element then wrap it in a
        # paragraph.
        if not ALLOWED_LISTITEM_CHILD.match(text):
            return f"<listitem><para>{text}</para></listitem>\n"
        else:
            return f"<listitem>{text}</listitem>\n"

    def block_text(self, token, state):
        text = self.render_children(token, state)
        return text

    def emphasis(self, token, state):
        text = self.render_children(token, state)
        return f"<emphasis>{text}</emphasis>"

    def strong(self, token, state):
        text = self.render_children(token, state)
        return f"<emphasis role=\"strong\">{text}</emphasis>"

    def admonition(self, token, state):
        text = self.render_children(token, state)
        kind = token['attrs']['kind']
        if kind not in admonitions:
            raise NotImplementedError(f"admonition {kind} not supported yet")
        tag = admonitions[kind]
        # we don't keep whitespace here because usually we'll contain only
        # a single paragraph and the original docbook string is no longer
        # available to restore the trailer.
        return f"<{tag}><para>{text.rstrip()}</para></{tag}>"

    def block_quote(self, token, state):
        text = self.render_children(token, state)
        return f"<blockquote><para>{text}</para></blockquote>"

    def command(self, token, state):
        text = token['raw']
        return f"<command>{escape(text)}</command>"

    def option(self, token, state):
        text = token['raw']
        return f"<option>{escape(text)}</option>"

    def file(self, token, state):
        text = token['raw']
        return f"<filename>{escape(text)}</filename>"

    def var(self, token, state):
        text = token['raw']
        return f"<varname>{escape(text)}</varname>"

    def env(self, token, state):
        text = token['raw']
        return f"<envar>{escape(text)}</envar>"

    def manpage(self, token, state):
        page = token['raw']
        section = token['attrs']['section']

        title = f"<refentrytitle>{escape(page)}</refentrytitle>"
        vol = f"<manvolnum>{escape(section)}</manvolnum>"
        return f"<citerefentry>{title}{vol}</citerefentry>"

    # FIXME: is this still needed?
    def finalize(self, data):
        return "".join(data)


def p_command(md):
    COMMAND_PATTERN = r'\{command\}`(?P<command_code>.*?)`'

    def parse(self, m, state):
        state.append_token({'type': 'command', 'raw': m.group('command_code')})
        return m.end()

    md.inline.register('command', COMMAND_PATTERN, parse)


def p_file(md):
    FILE_PATTERN = r'\{file\}`(?P<file_code>.*?)`'

    def parse(self, m, state):
        state.append_token({'type': 'file', 'raw': m.group('file_code')})
        return m.end()

    md.inline.register('file', FILE_PATTERN, parse)


def p_var(md):
    VAR_PATTERN = r'\{var\}`(?P<var_code>.*?)`'

    def parse(self, m, state):
        state.append_token({'type': 'var', 'raw': m.group('var_code')})
        return m.end()

    md.inline.register('var', VAR_PATTERN, parse)
    # md.inline.rules.append('var')


def p_env(md):
    ENV_PATTERN = r'\{env\}`(?P<env_code>.*?)`'

    def parse(self, m, state):
        state.append_token({'type': 'env', 'raw': m.group('env_code')})
        return m.end()

    md.inline.register('env', ENV_PATTERN, parse)


def p_option(md):
    OPTION_PATTERN = r'\{option\}`(?P<option_code>.*?)`'

    def parse(self, m, state):
        state.append_token({'type': 'option', 'raw': m.group('option_code')})
        return m.end()

    md.inline.register('option', OPTION_PATTERN, parse)


def p_manpage(md):
    MANPAGE_PATTERN = r'\{manpage\}`(?P<manpage_code>.*?)\((?P<manpage_section>.+?)\)`'

    def parse(self, m, state):
        state.append_token({
            'type': 'manpage',
            'raw': m.group('manpage_code'),
            'attrs': {'section': m.group('manpage_section')}
        })
        return m.end()

    md.inline.register('manpage', MANPAGE_PATTERN, parse)


def p_admonition(md):
    ADMONITION_PATTERN = re.compile(r'^::: \{(?P<admonition_kind>[^\n]*?)\}\n(?P<admonition_text>.*?)^:::$\n*',
                                    flags=re.MULTILINE | re.DOTALL)

    def parse(self, m, state):
        state.appand_token({
            'type': 'admonition',
            'children': self.parse(m.group('admonition_text'), state),
            'attrs': {'kind': m.group('admonition_kind')}
        })
        return m.end()

    md.block.register('admonition_', ADMONITION_PATTERN, parse)


# Converts option documentation texts such that it contains only plain DocBook
# markup. Specifically, this will expand Markdown and AsciiDoc texts.
def convertOptions(options: List[JSON]) -> List[JSON]:
    md = mistune.create_markdown(renderer=Renderer(),
                                 plugins=[
                                     p_command, p_file, p_var, p_env, p_option,
                                     p_manpage, p_admonition
                                 ])
    adoc = AsciiDocAPI()
    adoc.options('--no-header-footer')

    def convertMarkdown(path: str, text: str) -> str:
        try:
            rendered = md(text)
            # keep trailing spaces so we can diff the generated XML to check for conversion bugs.
            return rendered.rstrip() + text[len(text.rstrip()):]
        except:
            print(f"error in {path}")
            raise

    def convertAsciiDoc(path: str, text: str) -> str:
        try:
            infile = StringIO(text)
            outfile = StringIO()
            adoc.execute(infile, outfile, backend='docbook5')
            rendered = outfile.getvalue()
            # keep trailing spaces so we can diff the generated XML to check for conversion bugs.
            return rendered.rstrip() + text[len(text.rstrip()):]
        except:
            print(f"error in {path}")
            raise

    # Removes a wrapping <simpara> element, if one exists. This is useful, e.g.,
    # when converted Markdown text needs to be embedded in context that
    # disallows <simpara>.
    def unwrapSimpara(s: str) -> str:
        return s.removeprefix("<simpara>").removesuffix("</simpara>")

    def optionIs(option: Dict[str, Any], key: str, typ: str) -> bool:
        if key not in option: return False
        if type(option[key]) != dict: return False
        if '_type' not in option[key]: return False
        return option[key]['_type'] == typ

    def optionIsRawText(option: Dict[str, Any], key: str) -> bool:
        return key in option and type(option[key]) == str

    for option in options:
        name = option['name']
        try:
            # Handle the `description` field.
            if optionIs(option, 'description', 'mdDoc'):
                option['description'] = convertMarkdown(
                    name, option['description']['text'])
            elif optionIs(option, 'description', 'asciiDoc'):
                option['description'] = convertAsciiDoc(
                    name, option['description']['text'])
            elif optionIsRawText(option,
                                 'description') and name == '_module.args':
                # Special case for Nixpkgs' _module.args, which is Markdown even
                # without marking it as such.
                option['description'] = convertMarkdown(
                    name, option['description'])
            elif optionIsRawText(option, 'description'):
                # Wrap a plain DocBook description inside a <para> element to
                # maintain backwards compatibility. Basically, this prevents
                # errors when a user uses the `</para><para>` idiom to create
                # paragraph breaks.
                docbook = option['description'].rstrip()
                option['description'] = f"<para>{docbook}</para>"

            # Handle the `example` field.
            if optionIs(option, 'example', 'literalMD'):
                docbook = convertMarkdown(name, option['example']['text'])
                option['example'] = {
                    '_type': 'literalDocBook',
                    'text': unwrapSimpara(docbook)
                }
            elif optionIs(option, 'example', 'literalAsciiDoc'):
                docbook = unwrapSimpara(
                    convertAsciiDoc(name, option['example']['text']))
                option['example'] = {
                    '_type': 'literalDocBook',
                    'text': unwrapSimpara(docbook)
                }

            # Handle the `default` field.
            if optionIs(option, 'default', 'literalMD'):
                docbook = convertMarkdown(name, option['default']['text'])
                option['default'] = {
                    '_type': 'literalDocBook',
                    'text': unwrapSimpara(docbook)
                }
            elif optionIs(option, 'default', 'literalAsciiDoc'):
                docbook = unwrapSimpara(
                    convertAsciiDoc(name, option['default']['text']))
                option['default'] = {
                    '_type': 'literalDocBook',
                    'text': unwrapSimpara(docbook)
                }
        except Exception as e:
            raise Exception(f"Failed to render option {name}: {str(e)}")

    return options


def docbookify_options_json():
    options = pivot(json.load(open(sys.argv[1], 'r')))
    overrides = pivot(json.load(open(sys.argv[2], 'r')))

    # merge both descriptions
    for (k, v) in overrides.items():
        cur = options.setdefault(k, v).value
        for (ok, ov) in v.value.items():
            if ok == 'declarations':
                decls = cur[ok]
                for d in ov:
                    if d not in decls:
                        decls += [d]
            elif ok == "type":
                # ignore types of placeholder options
                if ov != "_unspecified" or cur[ok] == "_unspecified":
                    cur[ok] = ov
            elif ov is not None or cur.get(ok, None) is None:
                cur[ok] = ov

    # don't output \u escape sequences for compatibility with Nix 2.3
    json.dump(list(convertOptions(unpivot(options))),
              fp=sys.stdout,
              ensure_ascii=False)


if __name__ == '__main__':
    docbookify_options_json()
