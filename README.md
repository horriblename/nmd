# nmd

This is a fork of [nmd](https://sr.ht/~rycee/nmd) which migrates to mistune v3 (from v2)

## Introduction

The nmd project is a standalone version of the documentation system
inside [NixOS][nixos]. It has been refactored to make it easier to
generate documentation for other projects that use the [NixOS module
system][nixos-modules].

Note, this project is still immature and lack some features.

## Bug Reports and Sending Patches

Bug reports and patches are managed through [my sourcehut public inbox][]
and [nmd tickets][].

[my sourcehut public inbox]: https://lists.sr.ht/~rycee/public-inbox
[nmd tickets]: https://todo.sr.ht/~rycee/nmd

## Development

The code is formatted using [nixfmt][]. The formatting can be applied
by running

``` console
$ nix develop -c p-format
```

## Examples

The `examples` directory gives some demonstration of how to use nmd.
The examples can be built using `nix-build`, for example,

``` console
$ nix-build ./example/minimal -A html
```

## Example output

[Home Manager Manual](https://rycee.gitlab.io/home-manager/)

[rycee's NUR manual](https://rycee.gitlab.io/nur-expressions/)

## License

This project is licensed under the terms of the [MIT license](LICENSE).

[nixfmt]: https://github.com/serokell/nixfmt
[nixos-modules]: https://nixos.org/nixos/manual/index.html#sec-writing-modules
[nixos]: https://nixos.org/
