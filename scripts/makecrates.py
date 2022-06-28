"""
makecrates.py
Copyright 2017-2019 Adam Greig
Licensed under the MIT and Apache 2.0 licenses.

Autogenerate the crate Cargo.toml, build.rs, README.md and src/lib.rs files
based on available YAML files for each STM32 family.

Usage: python3 scripts/makecrates.py devices/
"""

import os
import glob
import os.path
import argparse
import re
import yaml

VERSION = "0.15.1"
SVD2RUST_VERSION = "0.28.0"

CRATE_DOC_FEATURES = {
    "stm32f0": ["critical-section", "rt", "stm32f0x0", "stm32f0x1", "stm32f0x2", "stm32f0x8"],
    "stm32f1": ["critical-section", "rt", "stm32f100", "stm32f101", "stm32f102", "stm32f103", "stm32f107"],
    "stm32f2": ["critical-section", "rt", "stm32f215", "stm32f217"],
    "stm32f3": ["critical-section", "rt", "stm32f302", "stm32f303", "stm32f373"],
    "stm32f4": ["critical-section", "rt", "stm32f401", "stm32f407", "stm32f413", "stm32f469"],
    "stm32f7": ["critical-section", "rt", "stm32f7x3", "stm32f7x9"],
    "stm32h7": ["critical-section", "rt", "stm32h743", "stm32h743v", "stm32h747cm7"],
    "stm32l0": ["critical-section", "rt", "stm32l0x0", "stm32l0x1", "stm32l0x2", "stm32l0x3"],
    "stm32l1": ["critical-section", "rt", "stm32l100", "stm32l151", "stm32l162"],
    "stm32l4": ["critical-section", "rt", "stm32l4x1", "stm32l4x5"],
    "stm32l5": ["critical-section", "rt", "stm32l562"],
    "stm32g0": ["critical-section", "rt", "stm32g030", "stm32g070", "stm32g0b0", "stm32g041", "stm32g081", "stm32g0c1"],
    "stm32g4": ["critical-section", "rt", "stm32g431", "stm32g441", "stm32g474", "stm32g484"],
    "stm32mp1": ["critical-section", "rt", "stm32mp157"],
    "stm32wl": ["critical-section", "rt", "stm32wle5", "stm32wl5x_cm4"],
    "stm32wb": ["critical-section", "rt", "stm32wb55"],
    "stm32u5": ["critical-section", "rt", "stm32u575", "stm32u585"]
}

CRATE_DOC_TARGETS = {
    "stm32f0": "thumbv6m-none-eabi",
    "stm32f1": "thumbv7m-none-eabi",
    "stm32f2": "thumbv7m-none-eabi",
    "stm32f3": "thumbv7em-none-eabihf",
    "stm32f4": "thumbv7em-none-eabihf",
    "stm32f7": "thumbv7em-none-eabihf",
    "stm32h7": "thumbv7em-none-eabihf",
    "stm32l0": "thumbv6m-none-eabi",
    "stm32l1": "thumbv7m-none-eabi",
    "stm32l4": "thumbv7em-none-eabihf",
    "stm32l5": "thumbv8m.main-none-eabi",
    "stm32g0": "thumbv6m-none-eabi",
    "stm32g4": "thumbv7em-none-eabihf",
    "stm32mp1": "thumbv7em-none-eabihf",
    "stm32wl": "thumbv7em-none-eabi",
    "stm32wb": "thumbv7em-none-eabihf",
    "stm32u5": "thumbv8m.main-none-eabi",
}

CARGO_TOML_TPL = """\
[package]
edition = "2018"
name = "{crate}"
version = "{version}"
authors = ["Adam Greig <adam@adamgreig.com>", "stm32-rs Contributors"]
description = "Device support crates for {family} devices"
repository = "https://github.com/stm32-rs/stm32-rs"
readme = "README.md"
keywords = ["stm32", "svd2rust", "no_std", "embedded"]
categories = ["embedded", "no-std"]
license = "MIT/Apache-2.0"

[dependencies]
critical-section = {{ version = "1.0", optional = true }}
cortex-m = "0.7.6"
cortex-m-rt = {{ version = ">=0.6.15,<0.8", optional = true }}
vcell = "0.1.3"

[package.metadata.docs.rs]
features = {docs_features}
default-target = "{doc_target}"
targets = []

[features]
default = ["critical-section", "rt"]
rt = ["cortex-m-rt/device"]
{features}
"""

SRC_LIB_RS_TPL = """\
//! Peripheral access API for {family} microcontrollers
//! (generated using [svd2rust](https://github.com/rust-embedded/svd2rust)
//! {svd2rust_version})
//!
//! You can find an overview of the API here:
//! [svd2rust/#peripheral-api](https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api)
//!
//! For more details see the README here:
//! [stm32-rs](https://github.com/stm32-rs/stm32-rs)
//!
//! This crate supports all {family} devices; for the complete list please
//! see:
//! [{crate}](https://crates.io/crates/{crate})
//!
//! Due to doc build limitations, not all devices may be shown on docs.rs;
//! a representative few have been selected instead. For a complete list of
//! available registers and fields see: [stm32-rs Device Coverage](https://stm32-rs.github.io/stm32-rs/)

#![allow(non_camel_case_types)]
#![allow(non_snake_case)]
#![no_std]

mod generic;
pub use self::generic::*;

{mods}
"""

README_TPL = """\
# {crate}
This crate provides an autogenerated API for access to {family} peripherals.
The API is generated using [svd2rust] with patched svd files containing
extensive type-safe support. For more information please see the [main repo].

Refer to the [documentation] for full details.

[svd2rust]: https://github.com/rust-embedded/svd2rust
[main repo]: https://github.com/stm32-rs/stm32-rs
[documentation]: https://docs.rs/{crate}/latest/{crate}/

## Usage
Each device supported by this crate is behind a feature gate so that you only
compile the device(s) you want. To use, in your Cargo.toml:

```toml
[dependencies.{crate}]
version = "{version}"
features = ["{device}"]
```

The `rt` feature is enabled by default and brings in support for `cortex-m-rt`.
To disable, specify `default-features = false` in `Cargo.toml`.

In your code:

```rust
use {crate}::{device};

let mut peripherals = {device}::Peripherals::take().unwrap();
let gpioa = &peripherals.GPIOA;
gpioa.odr.modify(|_, w| w.odr0().set_bit());
```

For full details on the autogenerated API, please see:
https://docs.rs/svd2rust/{svd2rust_version}/svd2rust/#peripheral-api

## Supported Devices

| Module | Devices | Links |
|:------:|:-------:|:-----:|
{devices}
"""


BUILD_TPL = """\
use std::env;
use std::fs;
use std::path::PathBuf;
fn main() {{
    if env::var_os("CARGO_FEATURE_RT").is_some() {{
        let out = &PathBuf::from(env::var_os("OUT_DIR").unwrap());
        println!("cargo:rustc-link-search={{}}", out.display());
        let device_file = {device_clauses};
        fs::copy(device_file, out.join("device.x")).unwrap();
        println!("cargo:rerun-if-changed={{}}", device_file);
    }}
    println!("cargo:rerun-if-changed=build.rs");
}}
"""


def read_device_table():
    path = os.path.join(
        os.path.abspath(os.path.split(__file__)[0]), os.pardir,
        "stm32_part_table.yaml")
    with open(path, encoding='utf-8') as f:
        table = yaml.safe_load(f)
    return table


def make_device_rows(table, family):
    rows = []
    for device, dt in table[family].items():
        links = "[{}]({}), [st.com]({})".format(
            dt['rm'], dt['rm_url'], dt['url'])
        members = ", ".join(m for m in dt['members'])
        rows.append("| {} | {} | {} |".format(device, members, links))
    return "\n".join(sorted(rows))


def make_features(devices):
    return "\n".join("{} = []".format(d) for d in sorted(devices))


def make_mods(devices):
    return "\n".join('#[cfg(feature = "{0}")]\npub mod {0};\n'.format(d)
                     for d in sorted(devices))


def make_device_clauses(devices):
    return " else ".join("""\
        if env::var_os("CARGO_FEATURE_{}").is_some() {{
            "src/{}/device.x"
        }}""".strip().format(d.upper(), d) for d in sorted(devices)) + \
            " else { panic!(\"No device features selected\"); }"


def main(devices_path, yes, families):
    devices = {}

    for path in glob.glob(os.path.join(devices_path, "*.yaml")):
        yamlfile = os.path.basename(path)
        family = re.match(r'stm32[a-z]+[0-9]', yamlfile)[0]
        if family.startswith('stm32wl'):
            family = 'stm32wl'
        if family.startswith('stm32wb'):
            family = 'stm32wb'
        device = os.path.splitext(yamlfile)[0].lower()
        if len(families) == 0 or family in families:
            if family not in devices:
                devices[family] = []
            devices[family].append(device)

    table = read_device_table()

    dirs = ", ".join(x.lower()+"/" for x in devices)
    print("Going to create/update the following directories:")
    print(dirs)
    if not yes:
        input("Enter to continue, ctrl-C to cancel")

    for family in devices:
        devices[family] = sorted(devices[family])
        crate = family.lower()
        features = make_features(devices[family])
        clauses = make_device_clauses(devices[family])
        mods = make_mods(devices[family])
        ufamily = family.upper()
        cargo_toml = CARGO_TOML_TPL.format(
            family=ufamily, crate=crate, version=VERSION, features=features,
            docs_features=str(CRATE_DOC_FEATURES[crate]),
            doc_target=CRATE_DOC_TARGETS[crate])
        readme = README_TPL.format(
            family=ufamily, crate=crate, device=devices[family][0],
            version=VERSION, svd2rust_version=SVD2RUST_VERSION,
            devices=make_device_rows(table, family))
        lib_rs = SRC_LIB_RS_TPL.format(family=ufamily, mods=mods, crate=crate,
                                       svd2rust_version=SVD2RUST_VERSION)
        build_rs = BUILD_TPL.format(device_clauses=clauses)

        os.makedirs(os.path.join(crate, "src"), exist_ok=True)
        with open(os.path.join(crate, "Cargo.toml"), "w") as f:
            f.write(cargo_toml)
        with open(os.path.join(crate, "README.md"), "w") as f:
            f.write(readme)
        with open(os.path.join(crate, "src", "lib.rs"), "w") as f:
            f.write(lib_rs)
        with open(os.path.join(crate, "build.rs"), "w") as f:
            f.write(build_rs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-y",
                        help="Assume 'yes' to prompt",
                        action="store_true")
    parser.add_argument("devices",
                        help="Path to device YAML files")
    parser.add_argument('--families',
                        help="Families of components to generate crates for",
                        nargs='+',
                        required=False,
                        metavar='FAMILY',
                        default=[],
                        type=str)
    args = parser.parse_args()
    main(args.devices, args.y, args.families)
