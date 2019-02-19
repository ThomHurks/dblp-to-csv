#! /usr/bin/env python3

from lxml import etree
import argparse
import os
import csv
import time
import re
from typing import Dict, Tuple, Union

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


def existing_dir(dirname: str) -> str:
    if os.path.isdir(dirname):
        return dirname
    else:
        raise argparse.ArgumentTypeError("%s is not a valid directory!" % dirname)


def parse_args():
    parser = argparse.ArgumentParser(description='Parse the DBLP XML file and convert it to CSV')
    parser.add_argument('xml_filename', action='store', type=existing_file, help='The XML file that will be parsed',
                        metavar='xml_filename')
    parser.add_argument('dtd_filename', action='store', type=existing_file,
                        help='The DTD file used to parse the XML file', metavar='dtd_filename')
    parser.add_argument('outputfile', action='store', type=str, help='The output CSV file', metavar='outputfile')
    parser.add_argument('--annotate', action='store_true', required=False,
                        help='Write a separate annotated header with type information')
    parser.add_argument('--neo4j', action='store_true', required=False,
                        help='Headers become more Neo4J-specific and a neo4j-import shell script is generated for easy '
                             'importing. Implies --annotate.')
    parser.add_argument('--neo4j_dir', action='store', required=False, type=existing_dir,
                        help='Target neo4j DB directory for the generated neo4j-import shell script command.')
    parser.add_argument('--relations', action='store', required=False, type=str, nargs='+',
                        help='The element attributes that need to be turned into a relation instance to their element, '
                             'e.g. for author to article, editor to book, etc pass in: author editor')
    parsed_args = parser.parse_args()
    if parsed_args.neo4j:
        if not parsed_args.annotate:
            parsed_args.annotate = True
            print("--neo4j implies --annotate!")
        if not parsed_args.neo4j_dir:
            print("--neo4j_dir is a required argument when --neo4j is used!")
            exit(1)
    if parsed_args.relations:
        parsed_args.relations = set(parsed_args.relations)
        print("Will create relations for attribute(s:) %s" % (", ".join(sorted(list(parsed_args.relations)))))
    else:
        parsed_args.relations = set()
    return parsed_args


def get_elements(dtd_file) -> set:
    dtd = etree.DTD(dtd_file)
    elements = set()
    for el in dtd.iterelements():
        if el.type == 'element':
            elements.add(el.name)
    elements.remove('dblp')
    return elements


def open_outputfiles(elements: set, element_attributes: dict, output_filename: str, annotated: bool = False) -> dict:
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
                                           quoting=csv.QUOTE_NONNUMERIC, restval='', doublequote=False, escapechar='\\')
            if not annotated:
                output_writer.writeheader()
            output_files[element] = output_writer
    return output_files


def get_element_attributes(xml_file, elements: set) -> dict:
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"), attribute_defaults=True,
                              load_dtd=True)
    # turn it into an iterator
    context = iter(context)
    # get the root element
    event, root = next(context)
    data = dict()
    for element in elements:
        data[element] = set()
    current_tag = None
    for event, elem in context:
        if current_tag is None and event == "start" and elem.tag in elements:
            current_tag = elem.tag
            keys = elem.keys()
            if len(keys) > 0:
                keys = set(keys)
                attributes = data[current_tag]
                attributes.update(keys)
        elif current_tag is not None and event == "end":
            if elem.tag == current_tag:
                current_tag = None
            elif elem.tag is not None and elem.text is not None:
                if elem.tag == "id":
                    raise InvalidElementName("id", elem.tag, current_tag)
                attributes = data[current_tag]
                attributes.add(elem.tag)
                keys = elem.keys()
                if len(keys) > 0:
                    for key in keys:
                        attributes.add("%s-%s" % (elem.tag, key))
            root.clear()
    for element in elements:
        attributes = data[element]
        if len(attributes) == 0:
            data.pop(element)
        elif "id" in attributes:
            raise InvalidElementName("id", element, "root")
    return data


def parse_xml(xml_file, elements: set, output_files: Dict[str, csv.DictWriter], relation_attributes: set,
              annotate: bool = False) \
        -> Union[Tuple[dict, int, dict, dict], Tuple[dict, int]]:
    context = etree.iterparse(xml_file, dtd_validation=True, events=("start", "end"))
    # turn it into an iterator
    context = iter(context)
    # get the root element
    event, root = next(context)
    data = dict()
    relations = dict()
    current_tag = None
    multiple_valued_cells = set()
    unique_id = 0
    if annotate:
        array_elements = dict()
        element_types = dict()
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
                if len(data) > 0:
                    set_relation_values(relations, data, relation_attributes, unique_id)
                    for cell in multiple_valued_cells:
                        data[cell] = '|'.join(sorted(data[cell]))
                    data["id"] = unique_id
                    fix_characters(data)
                    output_files[current_tag].writerow(data)
                    if annotate and len(multiple_valued_cells) > 0:
                        element_cells = array_elements.get(current_tag)
                        if element_cells is None:
                            array_elements[current_tag] = multiple_valued_cells.copy()
                        else:
                            element_cells.update(multiple_valued_cells)
                    unique_id += 1
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
        return relations, unique_id, array_elements, element_types
    else:
        return relations, unique_id


def set_relation_values(relations: dict, data: dict, relation_attributes: set, to_id: int):
    if len(relation_attributes) == 0:
        return
    for column_name, attributes in data.items():
        if column_name in relation_attributes:
            relation = relations.get(column_name, dict())
            if isinstance(attributes, list):
                for attribute in attributes:
                    rel_instance = relation.get(attribute, set())
                    rel_instance.add(to_id)
                    relation[attribute] = rel_instance
            else:
                rel_instance = relation.get(attributes, set())
                rel_instance.add(to_id)
                relation[attributes] = rel_instance
            relations[column_name] = relation


def set_cell_value(data: dict, column_name: str, value: str, multiple_valued_cells: set):
    entry = data.get(column_name, None)
    if entry is None:
        data[column_name] = value
    else:
        if isinstance(entry, list):
            entry.append(value)
        else:
            data[column_name] = [entry, value]
            multiple_valued_cells.add(column_name)


def set_type_information(element_types: dict, current_tag: str, column_name: str, value: str):
    attribute_types = element_types.get(current_tag)
    if attribute_types is None:
        element_types[current_tag] = attribute_types = dict()
    types = attribute_types.get(column_name)
    if types is None:
        attribute_types[column_name] = types = set()
    types.add(get_type(value))


def fix_characters(data):
    """ Sadly some bibtex in the input is causing issues with CSV writing and subsequent parsing. The solution is to
     delete the escaping slashes of already-escaped quotes, such that the quote is not doubly-escaped later."""
    for key, value in data.items():
        if isinstance(value, str):
            fixed_value = value.replace("\\\"", "\"")
            if fixed_value != value:
                print("Replaced '%s' by '%s'" % (value, fixed_value))
                data[key] = fixed_value
        elif isinstance(value, list):
            for i, listvalue in enumerate(value):
                if isinstance(listvalue, str):
                    fixed_value = listvalue.replace("\\\"", "\"")
                    if fixed_value != listvalue:
                        print("Replaced '%s' by '%s'" % (listvalue, fixed_value))
                        value[i] = fixed_value


def get_type(string_value: str) -> type:
    """Attempt to handle types int, float, boolean and string, nothing more complex since output is CSV."""
    if str.isdigit(string_value):
        try:
            int(string_value)
            return int
        except ValueError:
            return str
    if get_type.re_number.fullmatch(string_value) is not None:
        try:
            float(string_value)
            return float
        except ValueError:
            return str
    if string_value.lower() == "true" or string_value.lower() == "false":
        return bool
    return str
get_type.re_number = re.compile("^\d+\.\d+$")


def write_annotated_header(array_elements: dict, element_types: dict, output_filename: str, neo4j_style: bool = False):
    (path, ext) = os.path.splitext(output_filename)
    for element, column_types in element_types.items():
        output_path = "%s_%s_header%s" % (path, element, ext)
        header = []
        array_columns = array_elements[element]
        columns = sorted(list(column_types.keys()))
        if neo4j_style:
            header.append(":ID" % element)
        else:
            columns.insert(0, "id")
            column_types["id"] = set(int)
        for column in columns:
            types = column_types[column]
            high_level_type = get_high_level_type(types)
            typename = type_to_string(high_level_type, neo4j_style)
            if column in array_columns:
                header.append("%s:%s[]" % (column, typename))
            else:
                header.append("%s:%s" % (column, typename))
        with open(output_path, "w") as output_file:
            output_file.write(';'.join(header))


def type_to_string(type_input: type, neo4j_style: bool = False) -> str:
    typematch = type_to_string.re_typename.fullmatch(str(type_input))
    if typematch is not None:
        typename = typematch.group(1)
        if typename == 'str':
            return "string"
        elif typename == 'int':
            if neo4j_style:
                return "int"
            else:
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


def generate_neo4j_import_command(target_dir, elements: set, output_filename: str):
    (path, ext) = os.path.splitext(output_filename)
    command = "neo4j-import --into %s --delimiter \";\" --array-delimiter \"|\" --ignore-empty-strings true " \
              "--id-type INTEGER" % target_dir
    for element in elements:
        command += " --nodes:%s \"%s_%s_header%s,%s_%s%s\"" % (element, path, element, ext, path, element, ext)
    return command


def write_relation_files(output_filename: str, relations: dict, unique_id: int):
    (path, ext) = os.path.splitext(output_filename)
    for column_name, relation in relations.items():
        output_path_node = "%s_%s%s" % (path, column_name, ext)
        output_path_relation = "%s_%s_relation%s" % (path, column_name, ext)
        with open(output_path_relation, "w") as output_file_relation:
            output_file_relation.write(":START_ID;:END_ID\n")
            with open(output_path_node, "w") as output_file_node:
                node_output_writer = csv.writer(output_file_node,
                                                delimiter=';', quoting=csv.QUOTE_NONNUMERIC,
                                                doublequote=False, escapechar='\\')
                output_file_node.write(":ID;%s:string\n" % column_name)
                for value, rel_instance in relation.items():
                    node_output_writer.writerow([unique_id, value.replace("\\\"", "\"")])
                    for to_id in rel_instance:
                        output_file_relation.write("%d;%d\n" % (unique_id, to_id))
                    unique_id += 1


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
        output_files = open_outputfiles(elements, element_attributes, args.outputfile, args.annotate)
        array_elements = None
        element_types = None
        with open(args.xml_filename, "rb") as xml_file:
            print("Parsing XML and writing to CSV files...")
            if args.annotate:
                (relations, unique_id, array_elements, element_types) = parse_xml(xml_file, elements, output_files,
                                                                                  args.relations, annotate=True)
            else:
                relations, unique_id = parse_xml(xml_file, elements, output_files, args.relations)
        if args.relations and relations and unique_id >= 0:
            print("Writing relation files...")
            write_relation_files(args.outputfile, relations, unique_id)
        if args.annotate and array_elements and element_types:
            print("Writing annotated headers...")
            write_annotated_header(array_elements, element_types, args.outputfile, args.neo4j)
            if args.neo4j:
                print("Generating neo4j-import command...")
                command = generate_neo4j_import_command(args.neo4j_dir, set(element_types.keys()), args.outputfile)
                print("Writing neo4j-import command to shell script file...")
                with open("neo4j_import.sh", "w") as command_file:
                    command_file.write("#!/bin/bash\n")
                    command_file.write(command)
        end_time = time.time()
        print("Done after %f seconds" % (end_time - start_time))
    else:
        print("Invalid input arguments.")
        exit(1)


if __name__ == "__main__":
    main()
