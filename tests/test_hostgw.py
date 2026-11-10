from sistema.hostgw import gateway_desde_ip, gateway_desde_rutas


def test_gateway_desde_ruta_por_defecto():
    lineas = [
        "Iface\tDestination\tGateway\tFlags\tRefCnt\tUse\tMetric\tMask",
        "eth0\t00000000\t010013AC\t0003\t0\t0\t0\t00000000",
    ]
    assert gateway_desde_rutas(lineas) == "172.19.0.1"


def test_gateway_desde_ip_y_mascara():
    assert gateway_desde_ip("172.19.0.6", "255.255.0.0") == "172.19.0.1"
    assert gateway_desde_ip("10.0.0.25", "255.255.255.0") == "10.0.0.1"


def test_sin_ruta_por_defecto():
    lineas = ["eth0\t0001A8C0\t00000000\t0001\t0\t0\t0\t00FFFFFF"]
    assert gateway_desde_rutas(lineas) is None
