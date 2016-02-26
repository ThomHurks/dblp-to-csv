#! /usr/bin/env python3

from lxml import etree
import argparse
import os
import csv
import time

__author__ = 'Thom Hurks'


def existing_file(filename):
    if os.path.isfile(filename):
        return filename
    else:
        raise argparse.ArgumentTypeError("%s is not a valid input file!" % filename)


def parse_args():
    parser = argparse.ArgumentParser(description='Parse the DBLP XML file and convert it to CSV')
    parser.add_argument('xml_filename', action='store', type=existing_file, help='The XML file that will be parsed',
                        metavar='xml_filename')
    parser.add_argument('dtd_filename', action='store', type=existing_file,
                        help='The DTD file used to parse the XML file', metavar='dtd_filename')
    parser.add_argument('outputfile', action='store', type=str, help='The output CSV file', metavar='outputfile')
    return parser.parse_args()


def get_elements(dtd_file):
    dtd = etree.DTD(dtd_file)
    elements = set()
    for el in dtd.iterelements():
        if el.type == 'element':
            elements.add(el.name)
    elements.remove('dblp')
    return elements


def parse_xml(xml_file, elements, output_file):
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"))

    # turn it into an iterator
    context = iter(context)

    # get the root element
    event, root = next(context)
    print(root)

    attributes = set()
    fieldnames = ['title', 'ee', 'series', 'year', 'volume', 'sub', 'author', 'cdrom', 'month', 'cite', 'isbn',
                  'school', 'url', 'chapter', 'sup', 'publisher', 'pages', 'editor', 'crossref', 'number', 'journal',
                  'note', 'booktitle', 'address', 'tt', 'i']

    output_writer = csv.DictWriter(output_file, fieldnames=fieldnames, delimiter=';', quoting=csv.QUOTE_NONNUMERIC,
                                   restval='', extrasaction='ignore')
    output_writer.writeheader()
    data = dict()
    current_tag = None
    arrays = []
    for event, elem in context:
        if current_tag is None and event == "start" and elem.tag in elements:
            current_tag = elem.tag
            data.clear()
            arrays.clear()
            data['element'] = current_tag
        if current_tag is not None and event == "end":
            if elem.tag == current_tag:
                for a in arrays:
                    data[a] = ' | '.join(data[a])
                #print(data)
                #print('\n')
                current_tag = None
                output_writer.writerow(data)
            elif elem.tag is not None and elem.text is not None:
                attributes.add(elem.tag)
                entry = data.get(elem.tag, None)
                if entry is None:
                    data[elem.tag] = elem.text
                else:
                    if isinstance(entry, list):
                        entry.append(elem.text)
                        data[elem.tag] = entry
                    else:
                        data[elem.tag] = [entry, elem.text]
                        arrays.append(elem.tag)
            root.clear()
    print(attributes)


def main():
    args = parse_args()
    if args.xml_filename is not None and args.dtd_filename is not None and args.outputfile is not None:
        start_time = time.time()
        dtd_file = open(args.dtd_filename, "rb")
        elements = get_elements(dtd_file)
        xml_file = open(args.xml_filename, "rb")
        outputfile = open(args.outputfile, "w")
        parse_xml(xml_file, elements, outputfile)
        end_time = time.time()
        print("Done after %f seconds" % (end_time - start_time))
    else:
        print("Give a valid filename.")
        exit(1)


if __name__ == "__main__":
    main()
