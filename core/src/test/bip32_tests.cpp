// Copyright (c) 2013-2022 The Bitcoin Core developers
// Distributed under the MIT software license, see the accompanying
// file COPYING or http://www.opensource.org/licenses/mit-license.php.

#include <boost/test/unit_test.hpp>

#include <clientversion.h>
#include <key.h>
#include <key_io.h>
#include <streams.h>
#include <test/util/setup_common.h>
#include <util/strencodings.h>

#include <string>
#include <vector>

namespace {

struct TestDerivation {
    std::string pub;
    std::string prv;
    unsigned int nChild;
};

struct TestVector {
    std::string strHexMaster;
    std::vector<TestDerivation> vDerive;

    explicit TestVector(std::string strHexMasterIn) : strHexMaster(strHexMasterIn) {}

    TestVector& operator()(std::string pub, std::string prv, unsigned int nChild) {
        vDerive.emplace_back();
        TestDerivation &der = vDerive.back();
        der.pub = pub;
        der.prv = prv;
        der.nChild = nChild;
        return *this;
    }
};

TestVector test1 =
  TestVector("000102030405060708090a0b0c0d0e0f")
    ("dgub8kXBZ7ymNWy2S8Q3jNgVjFUm5ZJ3QLLaSTdAA89ukSv7Q6MSXwE14b7Nv6eDpE9JJXinTKc8LeLVu19uDPrm5uJuhpKNzV2kAgncwo6bNpP",
     "dgpv51eADS3spNJh9Gjth94XcPwAczvQaDJs9rqx11kvxKs6r3Ek8AgERHhjLs6mzXQFHRzQqGwqdeoDkZmr8jQMBfi43b7sT3sx3cCSk5fGeUR",
     0x80000000)
    ("dgub8nnbYqHETn61ajXkw8Z8cHasQNrPnQpb85448DY2ie7PmNecxAm6BjTnhNCvZY3qJk1MKZ9Z5HQasQ83ARb99nmduT7dunvxgcvBFVHuvrq",
     "dgpv53uaD9MLudRgHssbttwAVS3GwpUkxHnsqUGqy793vX4PDKXvYQDKYS4988T7QEnCzUt7CaGi21e6UKoZnKgXyjna7To1h1aqkcqJBDM65ur",
     1)
    ("dgub8pxikcq7rUy5RBaCfPT1D2UXTkqVnSYt4PitiVJqfGubzv9kfyBQ9JN27SfVyUmBGTdQ6ybfBsu4Thrrdkm2qSbaCexVPRwEKMSxYLP2A41",
     "dgpv565hQvuEJLJk8Kv3d9q36Avw1CTrxKXAmnwgZNurs9rbSs34GCddVzxNYBeB1AZFSZdo1Ps96ibWcGKnufUWkuH1dEkjkmMhRR9fi7Po6B2",
     0x80000002)
    ("dgub8sZzo9eyZMpVHMNHuyrNa2Wfgui23z8sPvxZxpbzq9H3QmLsUj1q3juwfTrLRMCVcyj8iMaGZpU2v319LrJZttkQnYvdUNzv33N6dcqeZ8X",
     "dgpv58gyTTj61DA9zVi8skEQTAy5EMLPDs7A7LBMoiD232E2riEB4xU4QSWJ6DrnyQ4jx2fBbrp4X8RQqU4YVgPhszifyrKHuhbe2gttLnRB4a6",
     2)
    ("dgub8uoPdamvjqVUMpr1cF4TTXfymizkgaT4qQqsDn8U9aqemryEYViCFKNsLnqiq9ME6HrJrN4DcZN9UTM9S9jmcVDfhLUpJZtk3jGwnGkhd8u",
     "dgpv5AvNHtr3Bgq94yBra1SVLg8PKAd7rTRMYp4f4fjVMTneDorY8jARc1yDmYGFS4UB1pntDn3dRwsaJexzh6w45PJiP6QPTnRMBfN3rDUiyyH",
     1000000000)
    ("dgub8wXA7GPArxsftAdTindBmEfyZxa4W5G6dfERU4WcMfE9UzNd4uxrWRXvyckfgQRwZz8rMhz29m4k4skAY1EcTkNnZstu73UNrgts2MA5evC",
     "dgpv5Ce8maTHJpDLbJyJgZ1DeP8P7QCRfxEPM4TDJx7dZYB8vwFvf9R5s88HQQ3TLybFdEC9192aGzQhJpyNEAwnCLxFibAcahB4TzvQbJyp2im",
     0);

TestVector test2 =
  TestVector("fffcf9f6f3f0edeae7e4e1dedbd8d5d2cfccc9c6c3c0bdbab7b4b1aeaba8a5a29f9c999693908d8a8784817e7b7875726f6c696663605d5a5754514e4b484542")
    ("dgub8kXBZ7ymNWy2RjuNqXknBTCXKkSU5xbQ83QtT4tjiq2yh5Ndi5zwVVGyGCjCXUWGD5xaMzGHjiqkcnt8LamvDpJrZkWqpyXQV4TjDhfyo9Q",
     "dgpv51eADS3spNJh8tFDoJ8p4bevsC4qFqZgqSdgHxVkvhyy92FwJKTArBsKgvsqB2xLXUjqaZQHukqQr6VxB9o3o32pW1C7bPngcrpg75LUw8V",
     0)
    ("dgub8onvpqfirXo6x1VfyK8fFFc3giBinw5ggDAFcsvBoEtwP3pcHMM1eKrDqfh6KZWhRQSkEDG38ogimxJpDjULZQy8qoFWjKfncYaPesrSURc",
     "dgpv54uuV9jqJP8mf9qWw5Wh8Q4TE9p5xp3yPcP3TmXD17qvpzhusaoF12SaGS9dp6oAw8yfUZp2LvFYCc8mjSJ6jGCDWBcAysxRkGjEUK7pYvw",
     0xFFFFFFFF)
    ("dgub8pwz5ShFERyD7shrPm8JibHc5TQdLRFNmNEnYGpxSyfKqM44uEmKrPdpT3wD5J7oCvNHt47eS27KSdB9zdxTHZRmNssa63voUvqzVgkMK7p",
     "dgpv564xjkmMgHJsq23hMXWLbjk1cu2zWJDfUmTaPARyercKHHwNVUDZD6EAsndcYMXeqNJZFb1fPvkedqsYTouEJZdmvuqWkPggY44mEn4uizf",
     1)
    ("dgub8skxVTgBQ5GQDVNzTRGsgYDqQzH8ScAe5ojePLVHks1mWAvECkJ2kJ2CHr8LsAp5o6pqihCt59R9XRSAuYPQYttfyA5RJbN1QhWwkCcvPdA",
     "dgpv58sw9mkHqvc4vdiqRBeuZggExRuVcV8voCxSEE6Jxjxkx7oXnykG6zcYiaqEa4jM9KfFzt63oURrxYehWhRcK3T54gNKbVf51rVViRSkahZ",
     0xFFFFFFFE)
    ("dgub8tvzQRcY1UE7WScbBu6R43v2KikVVao97WTXv4BhbdH1xXFAJRE3GpPHvWFr4YLXkYUUXCGb7kk1B4bZbRVvGFb8F4PurtTRGvbXH6bMPN3",
     "dgpv5A3y4jgeTKZnDaxS9fUSwCNRsANrfTmRpugKkwnioWE1QU8TtegGdWyeMHZdCV7dgtwxJhs3Br1Smfk52eL6zt8EtcudjhghMSW1nDNfmHP",
     2)
    ("dgub8vJ2Mrq3XeYMFhoUuyE72oHzinHbjuiDmg5RKqYCER8c2iajU49oTPLHzuL8C7hEGbgho7n11TkzfVf4RXBpaWShtEDzoFk9xDnhwhVSxT7",
     "dgpv5BR12Au9yVt1xr9Ksjc8uwkQGDuxungWV5JDAj9DSJ5bUfU34Hc2p5veRhEdMWChjCogbTVrdwr8pDdakxhL3rrxhUR8o7pR3oqZrnPNxDt",
     0);

TestVector test3 =
  TestVector("4b381541583be4423346c643850da4b320e46a87ae3d2a4e6da11eba819cd4acba45d239319ac14f863b8d5ab5a0d0c64d2e8a1e7d1457df2e5a3c51c73235be")
    ("dgub8kXBZ7ymNWy2QoMYMvFaPSTZCPmZqpkfqPBSrMvHzX7mfKbuNEEuSkWVkCGBM55uPAiSBz9J8Pfc46X3BHpMe9xzgzR4ZXyFGmyRk9hwu9B",
     "dgpv51eADS3spNJh7whPKgdcGauxjqPw1hixYnQEhFXKCQ4m7GVCxTh8oT6rAvc184BfcBQb9V6PpBa8Ck7GQawUaWY52Hkknq8euaV2kyg8TB3",
      0x80000000)
    ("dgub8ntPJ5ou3tLNcLSwb4b5ShDDtkNwzgAaEsRPfbc8vq38vLjMwj1mXDJD3v6h5RgeaYDGxwu2yLs6gZTP7XkYDQEwN6Mx7PU3kxLLQaYubK9",
     "dgpv541MxPt1Vjg3KUnnYpy7KqfdSC1KAZ8rxGeBWVDA8hz8NHcfXxTzsutZUgxMU1Wb4L41ARtGTvCarHkQyoXELGjhTRfoXzQU2bSgiK5zPHD",
      0);

TestVector test4 =
  TestVector("3ddd5602285899a946114506157c7997e5444528f3003f6134712147db19b678")
    ("dgub8kXBZ7ymNWy2Srs7CecPCBvSpdMjm5AR5WsrE6bss3xTWDREa8qfey4bSKWrNWfxxhqzLfNV5ASLryJAbVqGj1puTQi97qw4BNeeq3bAqhU",
     "dgpv51eADS3spNJhA1CxAQzR5LNrN4z6vx8hnv6e4zCu4vuSxAJYANHu1fews5t88narBeNDFfyXkWmtqkjZ4gCPfLCTXXcnqi2KBiMBX4mAnCN",
     0x80000000)
    ("dgub8ogHwW6RkH5U5jtEpyYACb2DGZF1UNgxppVWa4mrWW2RzkUM8UGPo1jwbuncQ936NocMHhm6g6NbPtzEJHHfpKswVj96zf2SEBChdQhyNHF",
     "dgpv54oGbpAYC8R8ntE5njvC5jUcozsNeFfFYDiJQxNsiNyRShMeihid9iLJ2doNBbmD9dPenF9m4xsynQveg3s2fy5PNuvU3dUKAyNzG3CMARs",
     0x80000001)
    ("dgub8qoybVVSG184ktjsyFT4JTc4SVR5yJPmUkYLLpJ4Ah7smqnrzxk728hpVrZ9FKfmxbDiBUhD8YiaNPK8kt6pXcpJqWz9xPWP6bZbgxLZnxL",
     "dgpv56vxFoZYhrTjU35iw1q6Bc4Tyw3T9BN4C9m8Bhu5Na4sDngAbCCLNqJAvbmTEzo3EPnkxqyiqbyrVNkN4yp9xMYcdFdV9fie2evgMXsARD8",
     0);

const std::vector<std::string> TEST5 = {
    "dgub8kXBZ7ymNWy2QnJWEQLHsawA7UgUAj8y2jCpiECsGPMXGz5yHHtQfjyATQgoZ6V42wYs42ZyXZg22jUCWNDKf4qfoVPgi9mBHuphP3y7k4k",
    "dgpv51eADS3spNJh7veMCAiKkjPZevJqLc7Fk8RcZ7otUGJWivyGsXLe2SZWtP4FUN876DxUXsKMGRwVbFXhMVx4LaxvqkbyFjNxpQUvTH57ZZT",
    "dgub8kXBZ7ymNWy2QnJWEQLHsawA7UgUAj8y2jCpiECsGPMXGz5yHHtQfjyATYTnG2HBSeFmbJto9tA1r1sJApgCFtDAx3g7gkWmGXrFMTyQ326",
    "dgpv51eADS3spNJh7veMCAiKkjPZevJqLc7Fk8RcZ7otUGJWivyGsXLe2SZWtPRMs2obwLyLZm8jRSDatf8bVjZtDq2EZWtTTX4WyhyaS1McYVP",
    "dgub8kXBZ7ymNWy2QnJWEQLHsawA7UgUAj8y2jCpiECsGPMXGz5yHHtQfjyATSdYjKw5tNE6Br9gS9J1z44yRUq3JmgYb8TnxJT5HZq5sfDRoci",
    "dgpv51eADS3spNJh7veMCAiKkjPZevJqLc7Fk8RcZ7otUGJWivyGsXLe2SZWtHb8LLTWP4wfAJPchhMb2hLGkPijGiVcCbg8j4zpzjxQxBChcoW",
    "dgpv51eb3AXyDTkzC8kGrRyNwAooDMBL5tqQEQUhFVrBbjvUvG6gzqfJUtgaJpACFxLXAEExLA5v7DJD4MCAd5dYhpYeryM1X2CBurdkE1RegM9",
    "dgub8kXcNrTrmcRKUzQRtfbM42MPfuYxv1s7X1FuQcFAPryVUKDPQcD58C6Dt6cUyCvjE7DRs6MRJySYXaj4pPauTT3ngJ8cX4iU213K97WRiHg",
    "dgpv51eADS3stAKqyadcLRFq2X5B5mvPsTXp8q68KYvhycMQv5nPCkXtc8bkcSegwNfx3YT26tR2okVXE412axRkTd7xCpBYaqNc2uCBvAmXdLw",
    "dgub8kXBZ7ymSJzBGSHmNeso9NcmYLJ2haZXRRsLUfKgmjQRU8u5cX5fFS1QBj6yedGA7RRVdpgY1WdrhHXvnGP7DFd628y9astt93bkqLcN4vX",
    "DMwo58pR1QLEFihHiXPVykYB6fJmsTeHvyTp7hRThAtCX8CvYzgPcn8XnmdfHGMQzT7ayAmfo4z3gY5KfbrZWZ6St24UVf2Qgo6oujFktLHdHY4",
    "DMwo58pR1QLEFihHiXPVykYB6fJmsTeHvyTp7hRThAtCX8CvYzgPcn8XnmdfHPmHJiEDXkTiJTVV9rHEBUem2mwVbbNfvT2MTcAqj3nesx8uBf9",
    "dgpv51eADS3spNJh7veMCAiKkjPZevJqLc7Fk8RcZ7otUGJWivyGsXLe2SZWtFePA71UXeGS2Uouo7jb5NjVqH71d1ejQxc2UvJw15x2SD4tn3a",
    "dgpv51eADS3spNJh7veMCAiKkjPZevJqLc7Fk8RcZ7otUGJWivyGsXLe2SZWtHb8LLTWP4wfAJPchhMb2hLCDXMpjhEpjtR9UDHWJSw3AQvv44D",
    "dgub8kXBZ7ymNWy2QnJWEQLHsawA7UgUAj8y2jCpiECsGPMXGz5yHHtQfjyATUaHuZP7jnuKKfjPLiv1wNfkLbSkxUXRNmXuCT8yHDqUMixfcDe",
    "xprv9s21ZrQH143K3QTDL4LXw2F7HEK3wJUD2nW2nRk4stbPy6cq3jPPqjiChkVvvNKmPGJxWUtg6LnF5kejMRNNU3TGtRBeJgk33yuGBxrMPHL"
};

void RunTest(const TestVector& test)
{
    std::vector<std::byte> seed{ParseHex<std::byte>(test.strHexMaster)};
    CExtKey key;
    CExtPubKey pubkey;
    key.SetSeed(seed);
    pubkey = key.Neuter();
    for (const TestDerivation &derive : test.vDerive) {
        unsigned char data[74];
        key.Encode(data);
        pubkey.Encode(data);

        // Test private key
        BOOST_CHECK(EncodeExtKey(key) == derive.prv);
        BOOST_CHECK(DecodeExtKey(derive.prv) == key); //ensure a base58 decoded key also matches

        // Test public key
        BOOST_CHECK(EncodeExtPubKey(pubkey) == derive.pub);
        BOOST_CHECK(DecodeExtPubKey(derive.pub) == pubkey); //ensure a base58 decoded pubkey also matches

        // Derive new keys
        CExtKey keyNew;
        BOOST_CHECK(key.Derive(keyNew, derive.nChild));
        CExtPubKey pubkeyNew = keyNew.Neuter();
        if (!(derive.nChild & 0x80000000)) {
            // Compare with public derivation
            CExtPubKey pubkeyNew2;
            BOOST_CHECK(pubkey.Derive(pubkeyNew2, derive.nChild));
            BOOST_CHECK(pubkeyNew == pubkeyNew2);
        }
        key = keyNew;
        pubkey = pubkeyNew;
    }
}

}  // namespace

BOOST_FIXTURE_TEST_SUITE(bip32_tests, BasicTestingSetup)

BOOST_AUTO_TEST_CASE(bip32_test1) {
    RunTest(test1);
}

BOOST_AUTO_TEST_CASE(bip32_test2) {
    RunTest(test2);
}

BOOST_AUTO_TEST_CASE(bip32_test3) {
    RunTest(test3);
}

BOOST_AUTO_TEST_CASE(bip32_test4) {
    RunTest(test4);
}

BOOST_AUTO_TEST_CASE(bip32_test5) {
    for (const auto& str : TEST5) {
        auto dec_extkey = DecodeExtKey(str);
        auto dec_extpubkey = DecodeExtPubKey(str);
        BOOST_CHECK_MESSAGE(!dec_extkey.key.IsValid(), "Decoding '" + str + "' as xprv should fail");
        BOOST_CHECK_MESSAGE(!dec_extpubkey.pubkey.IsValid(), "Decoding '" + str + "' as xpub should fail");
    }
}

BOOST_AUTO_TEST_CASE(bip32_max_depth) {
    CExtKey key_parent{DecodeExtKey(test1.vDerive[0].prv)}, key_child;
    CExtPubKey pubkey_parent{DecodeExtPubKey(test1.vDerive[0].pub)}, pubkey_child;

    // We can derive up to the 255th depth..
    for (auto i = 0; i++ < 255;) {
        BOOST_CHECK(key_parent.Derive(key_child, 0));
        std::swap(key_parent, key_child);
        BOOST_CHECK(pubkey_parent.Derive(pubkey_child, 0));
        std::swap(pubkey_parent, pubkey_child);
    }

    // But trying to derive a non-existent 256th depth will fail!
    BOOST_CHECK(key_parent.nDepth == 255 && pubkey_parent.nDepth == 255);
    BOOST_CHECK(!key_parent.Derive(key_child, 0));
    BOOST_CHECK(!pubkey_parent.Derive(pubkey_child, 0));
}

BOOST_AUTO_TEST_SUITE_END()
