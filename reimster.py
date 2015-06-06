#!/usr/bin/python3

import os.path
import re
import xml.parsers.expat as expat
import collections
import pathlib
import pickle
import operator as op
import math

import marisa_trie


def handler_factory():
    _state = None
    _contents = collections.defaultdict(list)
    result = {}

    def start_element(name, attrs):
        nonlocal _state
        if name in ("title", "text", "ns"):
            _state = name

    def characters(content):
        if _state is not None:
            _contents[_state].append(content)

    def end_element(name):
        nonlocal _state
        if _state:
            _state = None
        elif name == "page":
            if _contents["ns"][0] == "0":
                text = "".join(_contents["text"])
                m = re.search(r"\{\{Sprache\|([^\}]+)\}\}", text)
                #if m is not None and m.group(1) == "Deutsch" and "{{Wortart|Konjugierte Form" not in text:
                if m is not None and m.group(1) == "Deutsch":
                    title = "".join(_contents["title"])
                    pronounciations = re.findall(r"\{\{Lautschrift\|([^\}]+)\}\}", text)
                    if pronounciations and pronounciations.count('…') != len(pronounciations):
                        # TODO: Maybe handle other pronounciations
                        result[title] = pronounciations[0][::-1]

            _contents.clear()

    return result, start_element, characters, end_element



def get_table(language_code):
    data_path = pathlib.Path("data")
    xml_file_glob = "{}wiktionary-*-pages-meta-current.xml".format(language_code)
    newest_xml_file = sorted(data_path.glob(xml_file_glob))[-1]
    xml_date = re.match(
        os.path.join("data", r"{}wiktionary-([^-]+)-pages-meta-current.xml".format(language_code)),
        str(newest_xml_file),
    ).group(1)
    table_path = data_path / "{language_code}-{date}.table".format(
        language_code=language_code,
        date=xml_date,
    )
    if table_path.exists():
        with table_path.open("rb") as tablef:
            table = pickle.load(tablef)
    else:
        trie, pronounciations = parse_to_trie_and_table(newest_xml_file)
        table = group_rhymes(trie, pronounciations)
        with table_path.open("wb") as tablef:
            pickle.dump(table, tablef, protocol=pickle.HIGHEST_PROTOCOL)

    return table


def parse_to_trie_and_table(filepath):
    parser = expat.ParserCreate(encoding="utf-8")
    parser.buffer_text = True
    result, parser.StartElementHandler, parser.CharacterDataHandler, parser.EndElementHandler = handler_factory()
    with filepath.open("rb") as f:
        parser.ParseFile(f)

    inverse_result = collections.defaultdict(list)

    for title, pronounciation in result.items():
        inverse_result[pronounciation].append(bytes(title, "utf-8"))

    trie = marisa_trie.BytesTrie(
        (word, pronounciation)
        for word, pronounciations in inverse_result.items()
        for pronounciation in pronounciations
    )
    table = {key.lower(): value for key, value in result.items()}
    return trie, table


def find_ending(reverse_pronounciation, _cache={}):
    if reverse_pronounciation not in _cache:
        vowels="iyɨʉɯuɪʏʊeøɘɵɤoəɛœɜɞʌɔæɐaɶɑɒ"
        last_emphasized_part = re.match(
            r"([^ˈˌ]+)".format(vowels=vowels),
            reverse_pronounciation
        ).group(1)
        ending = re.match(
            r"(.+?)[^{vowels}]*$".format(vowels=vowels),
            last_emphasized_part
        ).group(1)
        _cache[reverse_pronounciation] = ending
    return _cache[reverse_pronounciation]


def group_rhymes(trie, pronounciations):
    scored_rhymes_by_word = {}
    for word, word_pronounciation in pronounciations.items():
        if word in scored_rhymes_by_word:
            continue

        word_ending = find_ending(word_pronounciation)

        rhymes = [
            rhyme.decode("utf-8")
            for pronounciation, rhyme in trie.items(word_ending)
            if word_ending == find_ending(pronounciation)
        ]

        rhymes_trie = marisa_trie.Trie([r.lower()[::-1] for r in rhymes])
        scored_rhymes = []
        for rhyme in rhymes:
            prefixes = rhymes_trie.prefixes(rhyme.lower()[::-1])
            prefixed_by = rhymes_trie.keys(rhyme.lower()[::-1])
            score = math.pow(len(prefixed_by) / len(prefixes), 0.2)
            scored_rhymes.append((score, rhyme))

        scored_rhymes = list(reversed(sorted(scored_rhymes)))
        for rhyme in rhymes:
            scored_rhymes_by_word[rhyme.lower()] = scored_rhymes

    return scored_rhymes_by_word


def main():
    rhymes = get_table("de")
    try:
        while True:
            word = input("> ").lower()
            if word not in rhymes:
                print("'{}' is not in the word database.".format(word))
                continue
            print([rhyme for score, rhyme in rhymes[word]])
    except KeyboardInterrupt:
        pass

def js_format_seq(seq):
    return "[%s]" % ",".join(map(str, seq))


def to_js():
    rhymes = get_table("de")
    lines = ["r={};"]
    processed = set()
    for scores_rhymes in rhymes.values():
        _, first_rhyme = scores_rhymes[0]
        if first_rhyme.lower() in processed:
            continue
        js_current = "[%s]" % ",".join("[%r,%.2g]" % (r, s) for s, r in scores_rhymes)
        lines.append("c=%s;" % js_current)
        for score, rhyme in scores_rhymes:
            lines.append("r[%r]=c;" % rhyme.lower())
            processed.add(rhyme.lower())
    lines.append("rhymes=r;")

    return "\n".join(lines)


if __name__ == "__main__":
    #main()
    print(to_js())
