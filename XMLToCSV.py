#! /usr/bin/env python3

from lxml import etree
import argparse
import os
import csv
import time
import re
from typing import Dict, Optional, Tuple

__author__ = 'Thom Hurks'


class InvalidElementName(Exception):
    def __init__(self, invalid_element_name, tag_name, parent_name):
        self.invalid_element_name = invalid_element_name
        self.tag_name = tag_name
        self.parent_name = parent_name

    def __str__(self):
        return "Invalid name %s found in tag %s within element %s" % (repr(self.invalid_element_name),
                                                                      repr(self.tag_name),
                                                                      repr(self.parent_name))


def existing_file(filename: str) -> str:
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
    parser.add_argument('--annotate', action='store_true', required=False,
                        help='Write a separate annotated header with type information')
    return parser.parse_args()


def get_elements(dtd_file) -> set:
    dtd = etree.DTD(dtd_file)
    elements = set()
    for el in dtd.iterelements():
        if el.type == 'element':
            elements.add(el.name)
    elements.remove('dblp')
    return elements


def open_outputfiles(elements: set, element_attributes: dict, output_filename: str) -> dict:
    (path, ext) = os.path.splitext(output_filename)
    output_files = dict()
    for element in elements:
        fieldnames = element_attributes.get(element, None)
        if fieldnames is not None and len(fieldnames) > 0:
            fieldnames = sorted(list(fieldnames))
            fieldnames.insert(0, "id")
            output_path = "%s_%s%s" % (path, element, ext)
            output_file = open(output_path, "w")
            output_writer = csv.DictWriter(output_file, fieldnames=fieldnames, delimiter=';',
                                           quoting=csv.QUOTE_NONNUMERIC, restval='')
            output_writer.writeheader()
            output_files[element] = output_writer
    return output_files


def get_element_attributes(xml_file, elements: set) -> dict:
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
                keys = set(keys)
                if "id" in keys:
                    raise InvalidElementName("id", elem.tag, "root")
                attributes = data.get(current_tag, set())
                data[current_tag] = attributes.union(keys)
        elif current_tag is not None and event == "end":
            if elem.tag == current_tag:
                current_tag = None
            elif elem.tag is not None and elem.text is not None:
                if elem.tag == "id":
                    raise InvalidElementName("id", elem.tag, current_tag)
                attributes = data.get(current_tag, set())
                attributes.add(elem.tag)
                keys = elem.keys()
                if len(keys) > 0:
                    for key in keys:
                        attributes.add("%s-%s" % (elem.tag, key))
                data[current_tag] = attributes
            root.clear()
    return data


def parse_xml(xml_file, elements: set, output_files: Dict[str, csv.DictWriter], annotate: bool = False) \
        -> Optional[Tuple[dict, dict]]:
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"))
    # turn it into an iterator
    context = iter(context)
    # get the root element
    event, root = next(context)
    data = dict()
    current_tag = None
    multiple_valued_cells = set()
    unique_ids = dict()
    if annotate:
        array_elements = dict()
        element_types = dict()
    for key in output_files.keys():
        unique_ids[key] = -1
    for event, elem in context:
        if current_tag is None and event == "start" and elem.tag in elements:
            current_tag = elem.tag
            data.clear()
            multiple_valued_cells.clear()
            data.update(elem.attrib)
            if annotate:
                for (key, value) in elem.attrib.items():
                    set_type_information(element_types, current_tag, key, value)
        elif current_tag is not None and event == "end":
            if elem.tag == current_tag:
                for cell in multiple_valued_cells:
                    data[cell] = '|'.join(sorted(data[cell]))
                if annotate:
                    array_elements[current_tag] = array_elements.get(current_tag, set()).union(multiple_valued_cells)
                if len(data) > 0:
                    row_id = unique_ids[current_tag] = unique_ids[current_tag] + 1
                    data["id"] = row_id
                    output_files[current_tag].writerow(data)
                current_tag = None
            elif elem.tag is not None and elem.text is not None:
                set_cell_value(data, elem.tag, elem.text, multiple_valued_cells)
                if annotate:
                    set_type_information(element_types, current_tag, elem.tag, elem.text)
                for (key, value) in elem.attrib.items():
                    column_name = "%s-%s" % (elem.tag, key)
                    set_cell_value(data, column_name, value, multiple_valued_cells)
                    if annotate:
                        set_type_information(element_types, current_tag, column_name, value)
            root.clear()
    if annotate:
        return array_elements, element_types


def set_cell_value(data: dict, column_name: str, value: str, multiple_valued_cells: set):
    entry = data.get(column_name, None)
    if entry is None:
        data[column_name] = value
    else:
        if isinstance(entry, list):
            entry.append(value)
            data[column_name] = entry
        else:
            data[column_name] = [entry, value]
            multiple_valued_cells.add(column_name)


def set_type_information(element_types: dict, current_tag: str, column_name: str, value: str):
    attribute_types = element_types.get(current_tag, dict())
    types = attribute_types.get(column_name, set())
    types.add(get_type(value))
    attribute_types[column_name] = types
    element_types[current_tag] = attribute_types


def get_type(string_value: str) -> type:
    """Attempt to handle types int, float, boolean and string, nothing more complex since output is CSV."""
    if str.isdigit(string_value):
        try:
            int(string_value)
            return int
        except ValueError:
            return str
    splits = string_value.split(sep='.')
    if len(splits) == 2 and str.isdigit(splits[0]) and str.isdigit(splits[1]):
        try:
            float(string_value)
            return float
        except ValueError:
            return str
    if string_value.lower() == "true" or string_value.lower() == "false":
        return bool
    return str


def write_annotated_header(array_elements: dict, element_types: dict, output_filename: str):
    (path, ext) = os.path.splitext(output_filename)
    for element, column_types in element_types.items():
        output_path = "%s_%s_header%s" % (path, element, ext)
        header = []
        array_columns = array_elements[element]
        columns = sorted(list(column_types.keys()))
        columns.insert(0, "id")
        column_types["id"] = {type(0)}
        for column in columns:
            types = column_types[column]
            high_level_type = get_high_level_type(types)
            typename = type_to_string(high_level_type)
            if column in array_columns:
                header.append("%s:%s[]" % (column, typename))
            else:
                header.append("%s:%s" % (column, typename))
        with open(output_path, "w") as output_file:
            output_file.write(','.join(header))


def type_to_string(type_input: type) -> str:
    typematch = type_to_string.re_typename.fullmatch(str(type_input))
    if typematch is not None:
        typename = typematch.group(1)
        if typename == 'str':
            return "string"
        elif typename == 'int':
            return "integer"
        elif typename == 'bool':
            return "boolean"
        else:
            return typename
    else:
        raise Exception("Unknown Type", type_input)
type_to_string.re_typename = re.compile('^<class \'([a-z]+)\'>$')


def get_high_level_type(types: set):
    if len(types) == 0:
        raise Exception("Empty type set encountered", types)
    elif len(types) == 1:
        (high_level_type,) = types
        return high_level_type
    else:
        if str in types:
            return str
        elif len(types) == 2 and float in types and int in types:
            return float
        else:
            return str


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
            try:
                element_attributes = get_element_attributes(xml_file, elements)
            except InvalidElementName as e:
                element_attributes = None
                print(e)
                exit(1)
        print("Opening output files...")
        output_files = open_outputfiles(elements, element_attributes, args.outputfile)
        with open(args.xml_filename, "rb") as xml_file:
            print("Parsing XML and writing to CSV files...")
            if args.annotate:
                (array_elements, element_types) = parse_xml(xml_file, elements, output_files, annotate=True)
                print("Writing annotated headers...")
                write_annotated_header(array_elements, element_types, args.outputfile)
            else:
                parse_xml(xml_file, elements, output_files)
        end_time = time.time()
        print("Done after %f seconds" % (end_time - start_time))
    else:
        print("Invalid input arguments.")
        exit(1)


if __name__ == "__main__":
    main()
