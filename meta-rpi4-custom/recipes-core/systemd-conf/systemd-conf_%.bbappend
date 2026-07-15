FILESEXTRAPATHS:prepend := "${THISDIR}/files:"

SRC_URI += "file://10-static.network \
            file://vconsole.conf"

PACKAGECONFIG:remove = "dhcp-ethernet"

do_install:append() {
    install -d ${D}${systemd_unitdir}/network
    install -m 0644 ${WORKDIR}/10-static.network ${D}${systemd_unitdir}/network/10-static.network
    install -d ${D}${sysconfdir}
    install -m 0644 ${WORKDIR}/vconsole.conf ${D}${sysconfdir}/vconsole.conf
}

FILES:${PN} += "${systemd_unitdir}/network ${sysconfdir}/vconsole.conf"
