# Changelog

Generated from Git history with Git-cliff, grouped by commit date (UTC).

## 2026-11-13

### Dependency updates

- Update dhi.io/golang docker tag to v1.27.4 ([`cd75128`](https://github.com/GaviniSumanth/images/commit/cd75128d5c5ad1379234134797e653641c012061))

## 2026-11-09

### Dependency updates

- Update renovatebot/github-action action to v46.3.13 ([`4cbb386`](https://github.com/GaviniSumanth/images/commit/4cbb386bd9adbc5f16cf8cabc5ed456b39984390))

### Bug fixes

- Update asset path in build context preparation ([`19791e4`](https://github.com/GaviniSumanth/images/commit/19791e471723b790b290b078f26eb31059b2acf7))

### Refactoring

- Move image build definitions under images/ ([`2c5f8b0`](https://github.com/GaviniSumanth/images/commit/2c5f8b03be2873df7c8f67a89c781dd06d8968bb))

### Other changes

- Enforce strict conventional commit policy ([`1104118`](https://github.com/GaviniSumanth/images/commit/110411886bc09f16274d0e99a55d5c3df44aaad3))
- Add changelog workflow ([`de0c5a1`](https://github.com/GaviniSumanth/images/commit/de0c5a1955cc6d9de38cd41e384713cf04d61c40))

## 2026-11-08

### Dependency updates

- Update Node.js to 3e61a81 ([`f878a9c`](https://github.com/GaviniSumanth/images/commit/f878a9cc1b82654d74322cfe24b833e22676ac72))
- Update dhi.io/rust:1-alpine-dev Docker digest to 7754008 ([`33bc8d2`](https://github.com/GaviniSumanth/images/commit/33bc8d23322337ff68cd46b883533656769b4a02))
- Update dhi.io/golang:1.27.3-alpine-dev Docker digest to 9589496 ([`f14a845`](https://github.com/GaviniSumanth/images/commit/f14a845c32136e637b8717a5b42d1442bbb69c2e))
- Update dhi.io/alpine-base:3.24-alpine3.24-dev Docker digest to 6930a22 ([`e2b823f`](https://github.com/GaviniSumanth/images/commit/e2b823ffec7067e9d71eaead18020f9daa86f112))
- Update Node.js to e640b13 ([`afd8a41`](https://github.com/GaviniSumanth/images/commit/afd8a41122b30d1be83275a9f6bf22c08cf63702))
- Update dhi.io/static:20261020-alpine Docker digest to 4767f88 ([`92808e0`](https://github.com/GaviniSumanth/images/commit/92808e0645114c1682151aa4ec8d1e3d20c648b3))
- Update Node.js to 7eb8c79 ([`1819d67`](https://github.com/GaviniSumanth/images/commit/1819d676fb11927d904dc503cbe93405a8315335))

### Other changes

- Clean up workflows ([`bf88c9b`](https://github.com/GaviniSumanth/images/commit/bf88c9b60ae18dc92044a0c1e47b5516aba6f675))

## 2026-11-07

### Dependency updates

- Pin dhi.io/alpine-base Docker tag to 52a1dd0 ([`48764a1`](https://github.com/GaviniSumanth/images/commit/48764a1f31461e357b71ee0ed6f937f3fa3ef554))
- Update dhi.io/golang:1.27.3-alpine-dev Docker digest to bc66efe ([`a7ce444`](https://github.com/GaviniSumanth/images/commit/a7ce444139bf495e9fd06b1c2e84d1fd3cd8798f))
- Pin dependencies ([`c9b9a5e`](https://github.com/GaviniSumanth/images/commit/c9b9a5e1b0720227143ee479cbf9c44d7e21348e))
- Update Node.js to 0057d01 ([`c799736`](https://github.com/GaviniSumanth/images/commit/c799736473e1d7d47f561732ec28b18721a2f8a2))
- Update dhi.io/golang Docker tag to v1.27.3 ([`6f75fb7`](https://github.com/GaviniSumanth/images/commit/6f75fb7708ada9e620ed5eeefe3a6d63cddee373))
- Update docker/login-action digest to 8aa5831 ([`3baf021`](https://github.com/GaviniSumanth/images/commit/3baf02152ab7ce2c8a1f8ed891c627d8fad1f8ec))

### Bug fixes

- Fix tests ([`ad64036`](https://github.com/GaviniSumanth/images/commit/ad64036f10d871e9c05d84bb8aef5f712a521533))
- Fix permission errors in tests ([`5ae4289`](https://github.com/GaviniSumanth/images/commit/5ae42897f5fc3a7ad120c3c23b2292158ec7cc6a))

### Refactoring

- Refactor workflow permissions ([`b6708ba`](https://github.com/GaviniSumanth/images/commit/b6708babfc531105ea04689cf0215072846732b0))

### Other changes

- Add qBittorrent image support with asset staging and tests ([`09f993f`](https://github.com/GaviniSumanth/images/commit/09f993fa1b8c47917ad80a3d6555c99c62b64968))
- Annotate zstd layers so publishing preserves the tested digest ([`8064f93`](https://github.com/GaviniSumanth/images/commit/8064f93899cd55e6082f4b09a9a9667a31925752))
- Unwrap the buildx layout index before publishing ([`8ffbb4e`](https://github.com/GaviniSumanth/images/commit/8ffbb4e631db119edff89da2460e204c1e63e5c1))
- Rebuild images whose published alias is missing ([`eadf7c5`](https://github.com/GaviniSumanth/images/commit/eadf7c5450e2068f75535186c28acd7cc0159122))
- Resolve image names from full references in contract checks ([`a32f16d`](https://github.com/GaviniSumanth/images/commit/a32f16d643cc70e306e6cb80ee8fa610669c5e0b))
- Make pipeline test environment deterministic ([`2e2d4e0`](https://github.com/GaviniSumanth/images/commit/2e2d4e02db011bc5f208048e12ade517ae86fd9c))
- Repo overhaul ([`999f576`](https://github.com/GaviniSumanth/images/commit/999f576c06404808c98d698954e2f7a435495c47))

## 2026-11-04

### Dependency updates

- Update Node.js to 8c18e7e ([`655b68f`](https://github.com/GaviniSumanth/images/commit/655b68f4b3c79649ca2d32045b01860928819909))
- Update Node.js to 6e0bd10 ([`1134cde`](https://github.com/GaviniSumanth/images/commit/1134cdef8bda711c3a5dc9653f90f4e322a9efa3))

### Features

- Fix gosu install ([`c103d82`](https://github.com/GaviniSumanth/images/commit/c103d8230dc86acdd5b0847ec2a01d2feb7cc391))
- Add new containerfiles and update releases.json for audiobookshelf, lldap, and authelia ([`f51ebe5`](https://github.com/GaviniSumanth/images/commit/f51ebe59595be29adbabffcc33575071e76170e6))

### Bug fixes

- Fix lldap issues ([`bb47d7e`](https://github.com/GaviniSumanth/images/commit/bb47d7e99445685dd7347f2e180b57a3bddf9625))
- Fix lldapdirectory creation ([`e4f5eca`](https://github.com/GaviniSumanth/images/commit/e4f5eca8978d65a5f1ec8cab6230c76957ddc355))

### Other changes

- Add directory for user share and copy timezone info ([`bed8c76`](https://github.com/GaviniSumanth/images/commit/bed8c76a3d89b443c2df96e06252f3b752ce0339))

## 2026-11-02

### Dependency updates

- Update renovatebot/github-action action to v46.3.12 ([`19e8132`](https://github.com/GaviniSumanth/images/commit/19e8132120125f92a3e96d9adc978a1f8d548884))

## 2026-11-01

### Dependency updates

- Pin dependencies ([`7baa4a8`](https://github.com/GaviniSumanth/images/commit/7baa4a8b50ef723f20a5c101a7aa0ee447976052))

### Bug fixes

- Fix build issue ([`2a77a60`](https://github.com/GaviniSumanth/images/commit/2a77a60d8c3658b61a6094f0857a3e0db99f2b6e))
- Fix audiobookshelf permission issues ([`8d5b65a`](https://github.com/GaviniSumanth/images/commit/8d5b65ab39713907a788af87dee5ec13c025f8f1))
- Test scripts and pipeline ([`e7fc7d9`](https://github.com/GaviniSumanth/images/commit/e7fc7d949a8c7c445ff35ff4eb4e45add037af65))
- Add tmpfs mount for FFmpeg runtime tests ([`9cb78b8`](https://github.com/GaviniSumanth/images/commit/9cb78b8f85be0d91b746906899f42094ab12cccb))
- Update test preparation command in run-tests.sh ([`32515d3`](https://github.com/GaviniSumanth/images/commit/32515d3c96170cc6448b718ca1d2ec7ab231945e))
- Fix path issues ([`5ca661d`](https://github.com/GaviniSumanth/images/commit/5ca661d4a58394095bd72a2eec5ec54dee90dc18))
- Correct custom manager type in enabledManagers from custom.jsonata to jsonata ([`ab1dae4`](https://github.com/GaviniSumanth/images/commit/ab1dae4ca495e9883f7c0c3d8fb004e258303408))
- Fix regex ([`c84eed6`](https://github.com/GaviniSumanth/images/commit/c84eed6c5be26a476ff13bf76a36039e1a58bb61))

### Reverts

- Revert "move renovate json" ([`6af15fb`](https://github.com/GaviniSumanth/images/commit/6af15fbc0f47c01963c7d01d3f0c9ae1bfd42d65))

### Other changes

- Update build pipeline for testing ([`0adfb2f`](https://github.com/GaviniSumanth/images/commit/0adfb2f1ae853499fc7086d0a5a941f50390a881))
- Update custom manager type from regex to jsonata in renovate configuration ([`ec2c127`](https://github.com/GaviniSumanth/images/commit/ec2c1270933ce5323293b8cea1742e6679a920e4))
- Update custom manager type from jsonata to regex in renovate configuration ([`c21fb75`](https://github.com/GaviniSumanth/images/commit/c21fb756b197ec76c42b25ebf5afb51e3a1456fe))
- Attempt jsonata duplication fix ([`e4c4e11`](https://github.com/GaviniSumanth/images/commit/e4c4e1186d6df1de3507394ab2bdb1c9e1ab4703))
- Update renovate ([`2527824`](https://github.com/GaviniSumanth/images/commit/252782421b6eaa27184850a89baedec6c7462b88))
- Update Renovate token to use RENOVATE_TOKEN ([`8f202f3`](https://github.com/GaviniSumanth/images/commit/8f202f3afa1ee169dbeb4bb9c779131b24d02d6f))
- Update renovate ([`2e4efc1`](https://github.com/GaviniSumanth/images/commit/2e4efc10b9452c1fb0565e89d0feb9aef3319b88))
- Add renovate env vars ([`2613501`](https://github.com/GaviniSumanth/images/commit/2613501428a8b5ae69be0ba2765572fa482f6255))
- Move renovate json ([`8b75043`](https://github.com/GaviniSumanth/images/commit/8b750436e890e80029eeda783cfaae22e5fc6c7e))
- Update renovate action ([`b810974`](https://github.com/GaviniSumanth/images/commit/b8109745363b4c5b164947b74394c6771efbb423))

## 2026-10-31

### Bug fixes

- Fix trivy platform ([`b7e7e6d`](https://github.com/GaviniSumanth/images/commit/b7e7e6d99b8ac8eed266543c8f1fd9f7d2cfd9e6))
- Fix config validation ([`581f987`](https://github.com/GaviniSumanth/images/commit/581f987be41e1f1a587a13f595c2dae050505f42))

### Other changes

- Update login action ([`ed28dcf`](https://github.com/GaviniSumanth/images/commit/ed28dcf55cf7d14a53fd65fefc183c14ad341496))
- Remove arm64 support ([`e270325`](https://github.com/GaviniSumanth/images/commit/e270325a0f1a77339a1914af790b57786b8ffbdf))
- Update GitHub Actions ([`ee2beaa`](https://github.com/GaviniSumanth/images/commit/ee2beaaafccc7e47f3378c878f28b4c8e3efeda9))
- Add audiobookshelf ([`8ae2552`](https://github.com/GaviniSumanth/images/commit/8ae2552a3754ccf5062628445965114df3566f29))
- Initial commit ([`003a471`](https://github.com/GaviniSumanth/images/commit/003a471f0edeb4e4a3d2f1ade823f3a2b155a11a))
