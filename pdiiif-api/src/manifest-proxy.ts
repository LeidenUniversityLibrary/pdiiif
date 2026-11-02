import { lookup } from 'dns/promises';
import { BlockList, isIP } from 'net';

const blockedIpv4Addresses = new BlockList();
for (const [address, prefix] of [
  ['0.0.0.0', 8],
  ['10.0.0.0', 8],
  ['100.64.0.0', 10],
  ['127.0.0.0', 8],
  ['169.254.0.0', 16],
  ['172.16.0.0', 12],
  ['192.0.0.0', 24],
  ['192.0.2.0', 24],
  ['192.168.0.0', 16],
  ['198.18.0.0', 15],
  ['198.51.100.0', 24],
  ['203.0.113.0', 24],
  ['224.0.0.0', 4],
  ['240.0.0.0', 4],
] as const) {
  blockedIpv4Addresses.addSubnet(address, prefix, 'ipv4');
}
const blockedIpv6Addresses = new BlockList();
for (const [address, prefix] of [
  ['::', 96],
  ['::ffff:0:0', 96],
  ['64:ff9b::', 96],
  ['2001::', 32],
  ['2001:db8::', 32],
  ['2002::', 16],
] as const) {
  blockedIpv6Addresses.addSubnet(address, prefix, 'ipv6');
}
const publicIpv6Addresses = new BlockList();
publicIpv6Addresses.addSubnet('2000::', 3, 'ipv6');

export class InvalidManifestUrlError extends Error {}

function isPublicAddress(address: string): boolean {
  const family = isIP(address);
  if (family === 4) {
    return !blockedIpv4Addresses.check(address, 'ipv4');
  }
  return (
    family === 6 &&
    publicIpv6Addresses.check(address, 'ipv6') &&
    !blockedIpv6Addresses.check(address, 'ipv6')
  );
}

/** Reject URLs that could make the public proxy contact a private service. */
export async function validateManifestUrl(manifestUrl: string): Promise<URL> {
  let url: URL;
  try {
    url = new URL(manifestUrl);
  } catch {
    throw new InvalidManifestUrlError('manifestUrl must be a valid URL');
  }
  if (
    !['http:', 'https:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    !url.hostname
  ) {
    throw new InvalidManifestUrlError('Only public HTTP(S) URLs are allowed');
  }

  const hostname = url.hostname.replace(/^\[|\]$/g, '');
  const addresses = isIP(hostname)
    ? [hostname]
    : (await lookup(hostname, { all: true })).map(({ address }) => address);
  if (!addresses.length || addresses.some((address) => !isPublicAddress(address))) {
    throw new InvalidManifestUrlError('Only public HTTP(S) URLs are allowed');
  }
  return url;
}

/** Validate each redirect target before the server requests it. */
export async function fetchPublicManifest(
  manifestUrl: string,
  acceptHeader?: string
): Promise<Response> {
  let url = manifestUrl;
  for (let redirectCount = 0; redirectCount <= 5; redirectCount += 1) {
    const validatedUrl = await validateManifestUrl(url);
    const response = await fetch(validatedUrl, {
      headers: acceptHeader ? { Accept: acceptHeader } : undefined,
      redirect: 'manual',
      signal: AbortSignal.timeout(20_000),
    });
    if (response.status < 300 || response.status >= 400) {
      return response;
    }
    const location = response.headers.get('location');
    if (!location) {
      return response;
    }
    url = new URL(location, validatedUrl).toString();
  }
  throw new InvalidManifestUrlError('Manifest URL redirected too many times');
}
