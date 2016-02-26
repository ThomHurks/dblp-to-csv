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


def open_outputfiles(elements, element_attributes, output_filename):
    (path, ext) = os.path.splitext(output_filename)
    output_files = dict()
    for element in elements:
        outputpath = "%s_%s%s" % (path, element, ext)
        outputfile = open(outputpath, "w")
        fieldnames = list(element_attributes[element])
        output_writer = csv.DictWriter(outputfile, fieldnames=fieldnames, delimiter=';', quoting=csv.QUOTE_NONNUMERIC,
                                       restval='')
        output_writer.writeheader()
        output_files[element] = output_writer
    return output_files


def get_element_attributes(xml_file, elements):
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"))

    # turn it into an iterator
    context = iter(context)

    # get the root element
    event, root = next(context)

    data = dict()
    current_tag = None
    for event, elem in context:
        if current_tag is None and event == "start" and elem.tag in elements:
            current_tag = elem.tag
            keys = elem.keys()
            if len(keys) > 0:
                attributes = data.get(current_tag, set())
                data[current_tag] = attributes.union(set(keys))
        elif current_tag is not None and event == "end":
            if elem.tag == current_tag:
                current_tag = None
            elif elem.tag is not None and elem.text is not None:
                attributes = data.get(current_tag, set())
                attributes.add(elem.tag)
                keys = elem.keys()
                if len(keys) > 0:
                    for key in keys:
                        attributes.add("%s-%s" % (elem.tag, key))
                data[current_tag] = attributes
            root.clear()
    return data


def parse_xml(xml_file, elements, output_files):
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"))
    # turn it into an iterator
    context = iter(context)
    # get the root element
    event, root = next(context)
    data = dict()
    current_tag = None
    multiple_valued_cells = []
    for event, elem in context:
        if current_tag is None and event == "start" and elem.tag in elements:
            current_tag = elem.tag
            data.clear()
            multiple_valued_cells.clear()
            data.update(elem.attrib)
        elif current_tag is not None and event == "end":
            if elem.tag == current_tag:
                for cell in multiple_valued_cells:
                    data[cell] = ' | '.join(data[cell])
                output_files[current_tag].writerow(data)
                current_tag = None
            elif elem.tag is not None and elem.text is not None:
                entry = data.get(elem.tag, None)
                if entry is None:
                    data[elem.tag] = elem.text
                else:
                    if isinstance(entry, list):
                        entry.append(elem.text)
                        data[elem.tag] = entry
                    else:
                        data[elem.tag] = [entry, elem.text]
                        multiple_valued_cells.append(elem.tag)
                # TODO: Probably want to check for multi-valued cells as well here.
                for (key, value) in elem.attrib.items():
                    data["%s-%s" % (elem.tag, key)] = value
            root.clear()


def main():
    args = parse_args()
    if args.xml_filename is not None and args.dtd_filename is not None and args.outputfile is not None:
        start_time = time.time()
        print("Start!")
        with open(args.dtd_filename, "rb") as dtd_file:
            print("Reading elements from DTD file...")
            elements = get_elements(dtd_file)
        with open(args.xml_filename, "rb") as xml_file:
            print("Finding unique attributes for all elements...")
            element_attributes = get_element_attributes(xml_file, elements)
        print("Opening output files...")
        output_files = open_outputfiles(elements, element_attributes, args.outputfile)
        with open(args.xml_filename, "rb") as xml_file:
            print("Parsing XML and writing to CSV files...")
            parse_xml(xml_file, elements, output_files)
        end_time = time.time()
        print("Done after %f seconds" % (end_time - start_time))
    else:
        print("Invalid input arguments.")
        exit(1)


if __name__ == "__main__":
    main()
