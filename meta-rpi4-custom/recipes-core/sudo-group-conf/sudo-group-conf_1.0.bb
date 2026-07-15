SUMMARY = "Grant sudo rights to the sudo group"
LICENSE = "MIT"
LIC_FILES_CHKSUM = "file://${COMMON_LICENSE_DIR}/MIT;md5=0835ade698e0bcf8506ecda2f7b4f302"

SRC_URI = "file://sudo-group"

S = "${WORKDIR}"

do_install() {
    install -d ${D}${sysconfdir}/sudoers.d
    install -m 0440 ${WORKDIR}/sudo-group ${D}${sysconfdir}/sudoers.d/sudo-group
}

RDEPENDS:${PN} = "sudo"
