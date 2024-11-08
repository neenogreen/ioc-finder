"""Python package for finding observables in text."""
import json
import re
import urllib.parse as urlparse
from typing import Dict, List
import click
import ioc_fanger
from d8s_strings import string_remove_from_end
from pyparsing import ParseResults, Located

from ioc_finder import ioc_grammars


def _deduplicate(indicator_list: List) -> List:
    """Deduplicate the list of observables."""
    return list(set(indicator_list))


def _listify_with_get_position(indicator_list: ParseResults, text: str) -> List:
    """Convert the multi-dimensional list into a one-dimensional list with empty entries and duplicates removed."""
    # dedup = _deduplicate([indicator[0][1] for indicator in indicator_list if indicator[0]])

    pos_map = {}
    to_dedup = []
    for indicator in indicator_list:
        tmp_pos = 0
        if len(indicator) > 0:
            position = [_.start() for _ in re.finditer(re.escape(indicator[0]), text,re.IGNORECASE)]
            if indicator[0] in to_dedup:
                continue
            to_dedup.append(indicator[0])
            for x in position:
                if pos_map.get(indicator[0]):
                    tmp_pos = x + len(indicator[0])
                    pos_map[indicator[0]].append([x, tmp_pos])
                else:
                    tmp_pos = x + len(indicator[0])
                    pos_map[indicator[0]] = [[x, tmp_pos]]
    return _deduplicate(to_dedup), pos_map


def _listify(indicator_list: ParseResults) -> List:
    """Convert the multi-dimensional list into a one-dimensional list with empty entries and duplicates removed."""
    # dedup = _deduplicate([indicator[0][1] for indicator in indicator_list if indicator[0]])
    pos_map = {}
    to_dedup = []
    for indicator in indicator_list:
        if len(indicator) > 0:
            to_dedup.append(indicator[1][0])
            if pos_map.get(indicator[1][0]):
                pos_map[indicator[1][0]].append([indicator[0], indicator[2]])
            else:
                pos_map[indicator[1][0]] = [[indicator[0], indicator[2]]]
    return _deduplicate(to_dedup), pos_map


def _remove_items(items: List[str], text: str) -> str:
    """Remove each item from the text."""
    for item in items:
        text = text.replace(item, " ")
    return text


def prepare_text(text: str) -> str:
    """Prepare the text for parsing.

    Currently, this involves fanging (https://ioc-fang.hightower.space/) the text."""
    text = ioc_fanger.fang(text)
    # text = text.encode('idna').decode('utf-8')
    return text


def parse_urls(
    text: str, *, parse_urls_without_scheme: bool = True, original_text: str
) -> List:
    """."""
    if parse_urls_without_scheme:
        urls = ioc_grammars.scheme_less_url.searchString(text)
    else:
        urls = ioc_grammars.url.searchString(text)
    urls, pos_map = _listify_with_get_position(urls, original_text)

    clean_urls = []

    # clean the url
    for url in urls:
        # save orginal url in order to track its position
        original_url = url
        # remove `"` and `'` characters from the end of a URL
        url = url.rstrip('"').rstrip("'")

        # remove a final ')' if there is a '(' in the url
        if url.endswith(")") and "(" not in url:
            url = url.rstrip(")")

        # remove `'/>` and `"/>` from the end of a URL (this character string occurs at the end of an HMTL tag with )
        url = string_remove_from_end(url, "'/>")
        url = string_remove_from_end(url, '"/>')
        if url != original_url:
            pos_map[url] = pos_map[original_url]
            del pos_map[original_url]
        clean_urls.append(url)

    # return the cleaned urls...
    # I deduplicate them again because the structure of the URL may have changed when it was cleaned
    return _deduplicate(clean_urls), pos_map


def _remove_url_domain_name(urls: List, text) -> str:
    """Remove the domain name of each url from the text."""
    for url in urls:
        parsed_url = ioc_grammars.scheme_less_url.parseString(url, text)
        text = text.replace(parsed_url.url_authority, " ")
    return text


def _remove_url_paths(urls: List, text: str, original_text: str) -> str:
    """Remove the path of each url from the text."""
    for url in urls:
        parsed_url = ioc_grammars.scheme_less_url.parseString(url)
        url_path = urlparse.unquote_plus(parsed_url.url_path)

        is_cidr_range = parse_ipv4_cidrs(str(url), original_text)
        # if the 'url' has a URL path and is not a cidr range, remove the url_path
        if not is_cidr_range and len(url_path) > 1:
            text = text.replace(url_path, " ")
    return text


def _percent_decode_url(urls: List, text: str) -> str:
    for url in urls:
        text = text.replace(url, urlparse.unquote_plus(url))
    return text


def parse_domain_names(text, original_text):
    """."""
    domains = ioc_grammars.domain_name.searchString(text.lower())
    return _listify_with_get_position(domains, original_text)


def parse_ipv4_addresses(text, original_text):
    """."""
    addresses = ioc_grammars.ipv4_address.searchString(text)
    return _listify_with_get_position(addresses, original_text)


def parse_ipv6_addresses(text, original_text):
    """."""
    addresses = ioc_grammars.ipv6_address.searchString(text)
    return _listify_with_get_position(addresses, original_text)


def parse_complete_email_addresses(text: str, original_text: str) -> List:
    """."""
    email_addresses = ioc_grammars.complete_email_address.searchString(text)
    return _listify_with_get_position(email_addresses, original_text)


def parse_email_addresses(text: str, original_text: str) -> List:
    """."""
    email_addresses = ioc_grammars.email_address.searchString(text)
    return _listify_with_get_position(email_addresses, original_text)


# there is a trailing underscore on this function to differentiate it from the argument with the same name
def parse_imphashes_(text: str, original_text: str) -> List:
    """."""
    full_imphash_instances = ioc_grammars.imphash.searchString(text.lower())
    full_imphash_instances, pos_map = _listify_with_get_position(
        full_imphash_instances, original_text
    )

    imphashes = []

    for imphash in full_imphash_instances:
        imphashes.append(ioc_grammars.imphash.parseString(imphash).hash[0])

    return imphashes, pos_map


# there is a trailing underscore on this function to differentiate it from the argument with the same name
def parse_authentihashes_(text: str, original_text: str) -> List:
    """."""
    full_authentihash_instances = ioc_grammars.authentihash.searchString(text.lower())
    full_authentihash_instances, pos_map = _listify_with_get_position(
        full_authentihash_instances, original_text
    )

    authentihashes = []

    for authentihash in full_authentihash_instances:
        authentihashes.append(
            ioc_grammars.authentihash.parseString(authentihash).hash[0]
        )

    return authentihashes, pos_map


def parse_md5s(text, original_text):
    """."""
    md5s = ioc_grammars.md5.searchString(text)
    return _listify_with_get_position(md5s, original_text)


def parse_sha1s(text, original_text):
    """."""
    sha1s = ioc_grammars.sha1.searchString(text)
    return _listify_with_get_position(sha1s, original_text)


def parse_sha256s(text, original_text):
    """."""
    sha256s = ioc_grammars.sha256.searchString(text)
    return _listify_with_get_position(sha256s, original_text)


def parse_sha512s(text, original_text):
    """."""
    sha512s = ioc_grammars.sha512.searchString(text)
    return _listify_with_get_position(sha512s, original_text)


def parse_ssdeeps(text, original_text):
    """."""
    ssdeeps = ioc_grammars.ssdeep.searchString(text)
    return _listify_with_get_position(ssdeeps, original_text)


def parse_asns(text, original_text):
    """."""
    asns = ioc_grammars.asn.searchString(text)
    return _listify_with_get_position(asns, original_text)


def parse_cves(text, original_text):
    """."""
    cves = ioc_grammars.cve.searchString(text)
    return _listify_with_get_position(cves, original_text)


def parse_ipv4_cidrs(text: str, original_text: str) -> List:
    """."""
    cidrs = ioc_grammars.ipv4_cidr.searchString(text)
    print(cidrs)
    return _listify_with_get_position(cidrs, original_text)


def parse_registry_key_paths(text, original_text):
    """."""
    parsed_registry_key_paths = ioc_grammars.registry_key_path.searchString(text)
    full_parsed_registry_key_paths, pos_map = _listify_with_get_position(
        parsed_registry_key_paths, original_text
    )

    registry_key_paths = []
    for registry_key_path in full_parsed_registry_key_paths:
        original_registry_key_path = registry_key_path
        # if there is a space in the last section of the parsed registry key path,
        # remove it so that content after a registry key path is not also pulled in...
        # this is a limitation of the grammar:
        # it will not parse a registry key path with a space in the final section (the section after the final '\')
        if " " in registry_key_path.split("\\")[-1]:
            last_section = registry_key_path.split("\\")[-1]
            registry_key_path = registry_key_path.replace(
                last_section, last_section.split(" ")[0]
            )
            registry_key_paths.append(registry_key_path)
            pos_map[registry_key_path] = pos_map[original_registry_key_path]
        else:
            registry_key_paths.append(registry_key_path)
    return registry_key_paths, pos_map


def parse_google_adsense_ids(text, original_text):
    """."""
    adsense_publisher_ids = ioc_grammars.google_adsense_publisher_id.searchString(text)
    return _listify_with_get_position(adsense_publisher_ids, original_text)


def parse_google_analytics_ids(text, original_text):
    """."""
    analytics_tracker_ids = ioc_grammars.google_analytics_tracker_id.searchString(text)
    return _listify_with_get_position(analytics_tracker_ids, original_text)


def parse_bitcoin_addresses(text, original_text):
    """."""
    bitcoin_addresses = ioc_grammars.bitcoin_address.searchString(text)
    return _listify_with_get_position(bitcoin_addresses, original_text)


def parse_monero_addresses(text, original_text):
    """."""
    monero_addresses = ioc_grammars.monero_address.searchString(text)
    return _listify_with_get_position(monero_addresses, original_text)


def parse_xmpp_addresses(text: str, original_text: str) -> List:
    """."""
    xmpp_addresses = ioc_grammars.xmpp_address.searchString(text)
    return _listify_with_get_position(xmpp_addresses, original_text)


def _remove_xmpp_local_part(xmpp_addresses: List, text: str) -> str:
    """Remove the local part of each xmpp_address from the text."""
    for address in xmpp_addresses:
        text = text.replace(address.split("@")[0] + "@", " ")

    return text


def parse_mac_addresses(text, original_text):
    """."""
    mac_addresses = ioc_grammars.mac_address.searchString(text)
    return _listify_with_get_position(mac_addresses, original_text)


def parse_user_agents(text, original_text):
    """."""
    user_agents = ioc_grammars.user_agent.searchString(text)
    return _listify_with_get_position(user_agents, original_text)


def parse_file_paths(text, original_text):
    """."""
    file_paths = ioc_grammars.file_path.searchString(text)
    return _listify_with_get_position(file_paths, original_text)


def parse_phone_numbers(text, original_text):
    """."""
    phone_numbers = ioc_grammars.phone_number.searchString(text[::-1])
    list_phone_numbers, pos_map = _listify_with_get_position(
        phone_numbers, original_text
    )

    clean_list_phone_numbers = []
    for phone_number in list_phone_numbers:
        clean_list_phone_numbers.append(phone_number[::-1])
        pos_map[phone_number[::-1]] = pos_map[phone_number]

    return clean_list_phone_numbers, pos_map


def digits_of(n):
    return [int(d) for d in str(n)]


def is_valid_credit_card(credit_card):
    credit_card = credit_card.replace("-", "").replace(" ", "")
    try:
        digits = digits_of(credit_card)
        odd_digits = digits[-1::-2]
        even_digits = digits[-2::-2]
        checksum = 0
        checksum += sum(odd_digits)
        for d in even_digits:
            checksum += sum(digits_of(d * 2))
        if checksum % 10 == 0:
            return True
        else:
            return False
    except:
        return False


def parse_credit_cards(text, original_text):
    """."""
    pattern = re.compile(r"[\d]+((-|\s)?[\d]+)+")
    credit_cards = []
    for x in re.finditer(pattern, text):
        candidate = str(x.group())
        if len(candidate) >= 14 and is_valid_credit_card(candidate):
            credit_cards.append([candidate])
    return _listify_with_get_position(credit_cards, original_text)


def parse_pre_attack_tactics(text):
    """."""
    data = ioc_grammars.pre_attack_tactics_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_pre_attack_techniques(text):
    """."""
    data = ioc_grammars.pre_attack_techniques_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_enterprise_attack_mitigations(text):
    """."""
    data = ioc_grammars.enterprise_attack_mitigations_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_enterprise_attack_tactics(text):
    """."""
    data = ioc_grammars.enterprise_attack_tactics_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_enterprise_attack_techniques(text):
    """."""
    data = ioc_grammars.enterprise_attack_techniques_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_mobile_attack_mitigations(text):
    """."""
    data = ioc_grammars.mobile_attack_mitigations_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_mobile_attack_tactics(text):
    """."""
    data = ioc_grammars.mobile_attack_tactics_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_mobile_attack_techniques(text):
    """."""
    data = ioc_grammars.mobile_attack_techniques_grammar.searchString(text)
    return _listify_with_get_position(data, text)


def parse_tlp_labels(text):
    """."""
    tlp_labels = ioc_grammars.tlp_label.searchString(text)
    return _listify_with_get_position(tlp_labels, text)


@click.command()
@click.argument("text", required=False)
@click.option(
    "--no_url_domain_parsing",
    is_flag=True,
    help="Using this flag will not parse domain names from URLs",
)
@click.option(
    "--no_parse_from_url_path",
    is_flag=True,
    help="Using this flag will not parse observables from URL paths",
)
@click.option(
    "--no_email_addr_domain_parsing",
    is_flag=True,
    help="Using this flag will not parse domain names from email addresses",
)
@click.option(
    "--no_cidr_address_parsing",
    is_flag=True,
    help="Using this flag will not parse IP addresses from CIDR ranges",
)
@click.option(
    "--no_xmpp_addr_domain_parsing",
    is_flag=True,
    help="Using this flag will not parse domain names from XMPP addresses",
)  # pylint: disable=R0913
@click.option(
    "--parse_urls_without_scheme",
    is_flag=True,
    help="Using this flag will parse URLs with and without a scheme (default is True)",
    default=True,
)
@click.option(
    "--no_import_hashes",
    is_flag=True,
    help="Using this flag will not parse import hashes",
)
@click.option(
    "--no_authentihashes",
    is_flag=True,
    help="Using this flag will not parse authentihashes",
)
def cli_find_iocs(
    text,
    no_url_domain_parsing,
    no_parse_from_url_path,
    no_email_addr_domain_parsing,
    no_cidr_address_parsing,
    no_xmpp_addr_domain_parsing,
    parse_urls_without_scheme,
    no_import_hashes,
    no_authentihashes,
):
    """CLI interface for parsing observables."""
    stdin_text = click.get_text_stream("stdin")

    # if there is stdin, use it
    if not text and stdin_text:
        text = "\n".join(stdin_text)
        # text = '\n'.join([line for line in stdin_text])

    iocs = find_iocs(
        text,
        parse_domain_from_url=not no_url_domain_parsing,
        parse_from_url_path=not no_parse_from_url_path,
        parse_domain_from_email_address=not no_email_addr_domain_parsing,
        parse_address_from_cidr=not no_cidr_address_parsing,
        parse_domain_name_from_xmpp_address=not no_xmpp_addr_domain_parsing,
        parse_urls_without_scheme=parse_urls_without_scheme,
        parse_imphashes=not no_import_hashes,
        parse_authentihashes=not no_authentihashes,
    )
    ioc_string = json.dumps(iocs, indent=4, sort_keys=True)


def find_iocs(  # noqa: CCR001 pylint: disable=R0912,R0915
    text: str,
    *,
    parse_domain_from_url: bool = True,
    parse_from_url_path: bool = True,
    parse_domain_from_email_address: bool = True,
    parse_address_from_cidr: bool = True,
    parse_domain_name_from_xmpp_address: bool = True,
    parse_urls_without_scheme: bool = True,
    parse_imphashes: bool = True,
    parse_authentihashes: bool = True,
) -> Dict[str, List]:
    """Find observables in the given text."""
    iocs = dict()

    # keep a copy of the original text - some items should be parsed from the original text
    original_text = text
    pos_map = {}
    # urls
    iocs["urls"], pos_map["urls"] = parse_urls(
        text,
        parse_urls_without_scheme=parse_urls_without_scheme,
        original_text=original_text,
    )
    if not parse_domain_from_url and not parse_from_url_path:
        text = _remove_items(iocs["urls"], text)
    elif not parse_domain_from_url:
        text = _percent_decode_url(iocs["urls"], text)
        text = _remove_url_domain_name(iocs["urls"], text)
    elif not parse_from_url_path:
        text = _percent_decode_url(iocs["urls"], text)
        text = _remove_url_paths(iocs["urls"], text, original_text)
    else:
        text = _percent_decode_url(iocs["urls"], text)

    # xmpp addresses
    iocs["xmpp_addresses"], pos_map["xmpp_addresses"] = parse_xmpp_addresses(
        text, original_text
    )
    if not parse_domain_name_from_xmpp_address:
        text = _remove_items(iocs["xmpp_addresses"], text)
    # even if we want to parse domain names from the xmpp_address,
    # we don't want them also being caught as email addresses so we'll remove everything before the `@`
    else:
        text = _remove_xmpp_local_part(iocs["xmpp_addresses"], text)

    # complete email addresses
    (
        iocs["email_addresses_complete"],
        pos_map["email_addresses_complete"],
    ) = parse_complete_email_addresses(text, original_text)
    # simple email addresses
    iocs["email_addresses"], pos_map["email_addresses"] = parse_email_addresses(
        text, original_text
    )
    if not parse_domain_from_email_address:
        text = _remove_items(iocs["email_addresses_complete"], text)
        text = _remove_items(iocs["email_addresses"], text)
    # after parsing the email addresses, we need to remove the
    # '[IPv6:' bit from any of the email addresses so that ipv6 addresses are not extraneously parsed
    text = _remove_items(["[IPv6:"], text)

    # cidr ranges

    # ATTENTION REMOVE POS_MAP_EMAIL_ADDRESES
    wasted = {}
    iocs["ipv4_cidrs"], wasted = parse_ipv4_cidrs(text, original_text)
    if not parse_address_from_cidr:
        text = _remove_items(iocs["ipv4_cidrs"], text)

    # remove URLs that are also ipv4_cidrs (see https://github.com/fhightower/ioc-finder/issues/91)
    if parse_urls_without_scheme:
        for cidr in iocs["ipv4_cidrs"]:
            if isinstance(cidr, str):
                cidr = [cidr]
            for cidr in cidr:
                if cidr in iocs["urls"]:
                    iocs["urls"].remove(cidr)
                    if cidr in pos_map["urls"]:
                        del pos_map["urls"][cidr]

    # file hashes
    if parse_imphashes:
        iocs["imphashes"], pos_map["imphashes"] = parse_imphashes_(text, original_text)
        # remove the imphashes so they are not also parsed as md5s
        text = _remove_items(iocs["imphashes"], text)

    if parse_authentihashes:
        iocs["authentihashes"], pos_map["authentihashes"] = parse_authentihashes_(
            text, original_text
        )
        # remove the authentihashes so they are not also parsed as sha256s
        text = _remove_items(iocs["authentihashes"], text)

    # domains
    iocs["domains"], pos_map["domains"] = parse_domain_names(text, original_text)
    iocs["credit-cards"], pos_map["credit-cards"] = parse_credit_cards(
        text, original_text
    )
    # ip addresses
    iocs["ipv4s"], pos_map["ipv4s"] = parse_ipv4_addresses(text, original_text)
    iocs["ipv6s"], pos_map["ipv6s"] = parse_ipv6_addresses(text, original_text)

    # file hashes
    iocs["sha512s"], pos_map["sha512s"] = parse_sha512s(text, original_text)
    iocs["sha256s"], pos_map["sha256s"] = parse_sha256s(text, original_text)
    iocs["sha1s"], pos_map["sha1s"] = parse_sha1s(text, original_text)
    iocs["md5s"], pos_map["md5s"] = parse_md5s(text, original_text)
    iocs["ssdeeps"], pos_map["ssdeeps"] = parse_ssdeeps(text, original_text)

    # misc
    iocs["asns"], pos_map["asns"] = parse_asns(text, original_text)
    iocs["cves"], pos_map["cves"] = parse_cves(original_text, original_text)
    (
        iocs["registry_key_paths"],
        pos_map["registry_key_paths"],
    ) = parse_registry_key_paths(text, original_text)
    (
        iocs["google_adsense_publisher_ids"],
        pos_map["google_adsense_publisher_ids"],
    ) = parse_google_adsense_ids(text, original_text)
    (
        iocs["google_analytics_tracker_ids"],
        pos_map["google_analytics_tracker_ids"],
    ) = parse_google_analytics_ids(text, original_text)
    iocs["bitcoin_addresses"], pos_map["bitcoin_addresses"] = parse_bitcoin_addresses(
        text, original_text
    )
    iocs["monero_addresses"], pos_map["monero_addresses"] = parse_monero_addresses(
        text, original_text
    )
    iocs["mac_addresses"], pos_map["mac_addresses"] = parse_mac_addresses(
        text, original_text
    )
    iocs["user_agents"], pos_map["user_agents"] = parse_user_agents(text, original_text)
    # iocs['phone_numbers'], pos_map['phone_numbers'] = parse_phone_numbers(text,original_text)
    iocs["tlp_labels"], pos_map["tlp_labels"] = parse_tlp_labels(original_text)

    # Da sistemare
    pos_map["attack_mitigations"] = {}
    pos_map["attack_tactics"] = {}
    pos_map["attack_techniques"] = {}

    (
        am_enterprise,
        pos_map["attack_mitigations"]["enterprise"],
    ) = parse_enterprise_attack_mitigations(original_text)
    (
        am_mobile,
        pos_map["attack_mitigations"]["mobile"],
    ) = parse_mobile_attack_mitigations(original_text)
    ata_pre_attack, pos_map["attack_tactics"]["pre_attack"] = parse_pre_attack_tactics(
        original_text
    )
    (
        ata_enterprise,
        pos_map["attack_tactics"]["enterprise"],
    ) = parse_enterprise_attack_tactics(original_text)
    ata_mobile, pos_map["attack_tactics"]["mobile"] = parse_mobile_attack_tactics(
        original_text
    )
    (
        ate_pre_attack,
        pos_map["attack_techniques"]["pre_attack"],
    ) = parse_pre_attack_techniques(original_text)
    (
        ate_enterprise,
        pos_map["attack_techniques"]["enterprise"],
    ) = parse_enterprise_attack_techniques(original_text)
    ate_mobile, pos_map["attack_techniques"]["mobile"] = parse_mobile_attack_techniques(
        original_text
    )

    iocs["attack_mitigations"] = {  # type: ignore
        "enterprise": am_enterprise,
        "mobile": am_mobile,
    }
    iocs["attack_tactics"] = {  # type: ignore
        "pre_attack": ata_pre_attack,
        "enterprise": ata_enterprise,
        "mobile": ata_mobile,
    }
    iocs["attack_techniques"] = {  # type: ignore
        "pre_attack": ate_pre_attack,
        "enterprise": ate_enterprise,
        "mobile": ate_mobile,
    }

    # if there are still url paths in the text, remove them so they don't get parsed as file names
    if parse_from_url_path:
        text = _remove_url_paths(iocs["urls"], text, original_text)

    iocs["file_paths"], pos_map["file_paths"] = parse_file_paths(text, original_text)

    return iocs, pos_map
