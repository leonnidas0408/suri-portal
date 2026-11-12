"""Compatibilidade para Buildozer que não encaminha extra-manifest-application-xml."""
from pathlib import Path

import buildozer.targets.android as android_target


PATCH_MARKER = "# support for extra-manifest-application-xml (Suri Portal)"
ANCHOR = "        # support for gradle dependencies\n"
PATCH = '''        # support for extra-manifest-application-xml (Suri Portal)
        extra_manifest_application_xml = self.buildozer.config.get(
            'app', 'android.extra_manifest_application_xml', fallback='')
        if extra_manifest_application_xml:
            cmd.append('--extra-manifest-application-xml')
            cmd.append(open(extra_manifest_application_xml, 'rt').read())

'''


def main():
    path = Path(android_target.__file__)
    source = path.read_text(encoding="utf-8")
    if PATCH_MARKER in source or "extra-manifest-application-xml" in source:
        print("Buildozer já encaminha extra-manifest-application-xml.")
        return
    if ANCHOR not in source:
        raise SystemExit("Não foi possível localizar o ponto de extensão esperado no Buildozer.")
    path.write_text(source.replace(ANCHOR, PATCH + ANCHOR, 1), encoding="utf-8")
    print("Buildozer ajustado para encaminhar o XML do FileProvider ao python-for-android.")


if __name__ == "__main__":
    main()
