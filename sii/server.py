# -*- coding: UTF-8 -*-

from sii.resource import SII
from zeep import Client
from requests import Session
from zeep.transports import Transport
from zeep.helpers import serialize_object


class Service(object):
    def __init__(self, certificate, key, proxy=None):
        self.certificate = certificate
        self.key = key
        self.proxy_address = proxy
        self.result = []


class IDService(Service):
    def __init__(self, proxy, certificate, key):
        super(IDService, self).__init__(certificate, key, proxy)
        self.validator_service = None

    def ids_validate(self, partners):
        self.validator_service = self.create_validation_service(partners)
        try:
            if isinstance(partners, list):
                if len(partners) > 10000:
                    chunks = [list[i:i + 10000] for i in range(0, len(list), 10000)]
                    for chunk in chunks:
                        self.send_validate_chunk(chunk=chunk)
                else:
                    self.send_validate_chunk(partners)
            else:
                partners['Nif'] = partners.pop('vat')
                partners['Nombre'] = partners.pop('name')
                self.result = serialize_object(
                    self.validator_service.VNifV1(
                        partners['Nif'], partners['Nombre']
                    )
                )
            return serialize_object(self.result)
        except Exception as fault:
            self.result = fault

    def send_validate_chunk(self, chunk):
        for partner in chunk:
            partner['Nif'] = partner.pop('vat')
            partner['Nombre'] = partner.pop('name')
        self.result.extend(self.validator_service.VNifV2(chunk))

    def invalid_ids(self, partners):
        self.ids_validate(partners)
        invalid_ids = []
        if isinstance(partners, list):
            for partner in self.result:
                if partner['Resultado'] == 'NO IDENTIFICADO':
                    invalid_ids.append(partner)
        else:
            if isinstance(self.result, Exception) and self.result.message == 'Codigo[-1].No identificado':
                return partners
        return serialize_object(invalid_ids)

    def create_validation_service(self, partners):
        port_name = 'VNifPort1'
        type_address = '/wlpl/BURT-JDIT/ws/VNifV1SOAP'
        binding_name = '{http://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV1.wsdl}VNifV1SoapBinding'
        service_name = 'VNifV1Service'
        wsdl = self.wsdl_files['ids_validator_v1']
        if isinstance(partners, list):
            type_address = '/wlpl/BURT-JDIT/ws/VNifV2SOAP'
            binding_name = '{http://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV2.wsdl}VNifV2SoapBinding'
            service_name = 'VNifV2Service'
            wsdl = self.wsdl_files['ids_validator_v2']
        session = Session()
        session.cert = (self.certificate, self.key)
        session.verify = False
        transport = Transport(session=session)

        client = Client(wsdl=wsdl, port_name=port_name, transport=transport,
                        service_name=service_name)
        address = '{0}{1}'.format(self.proxy_address, type_address)
        service = client.create_service(binding_name, address)
        return service

    wsdl_files = {
        'ids_validator_v1': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV1.wsdl',
        'ids_validator_v2': 'https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/burt/jdit/ws/VNifV2.wsdl'
    }


class SiiService(Service):
    def __init__(self, proxy, certificate, key, test_mode=False):
        super(SiiService, self).__init__(certificate, key, proxy)
        self.test_mode = True  # Force now work in test mode
        self.emitted_service = None
        self.received_service = None
        self.proxy_address = proxy
        self.invoice = None

    def send(self, invoice):
        self.invoice = invoice
        if self.invoice.type.startswith('out_'):
            if self.emitted_service is None:
                self.emitted_service = self.create_service()
        else:
            if self.received_service is None:
                self.received_service = self.create_service()
        return self.send_invoice()

    def create_service(self):
        session = Session()
        session.cert = (self.certificate, self.key)
        session.verify = False
        transport = Transport(session=session)
        if self.invoice.type.startswith('out_'):
            wsdl = self.wsdl_files['emitted_invoice']
            port_name = 'SuministroFactEmitidas'
            binding_name = '{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroFactEmitidas.wsdl}siiBinding'
            type_address = '/wlpl/SSII-FACT/ws/fe/SiiFactFEV1SOAP'
        else:
            wsdl = self.wsdl_files['received_invoice']
            port_name = 'SuministroFactRecibidas'
            binding_name = '{https://www2.agenciatributaria.gob.es/static_files/common/internet/dep/aplicaciones/es/aeat/ssii/fact/ws/SuministroFactRecibidas.wsdl}siiBinding'
            type_address = '/wlpl/SSII-FACT/ws/fr/SiiFactFRV1SOAP'
        if self.test_mode:
            port_name += 'Pruebas'

        client = Client(wsdl=wsdl, port_name=port_name, transport=transport,
                        service_name='siiService')
        address = '{0}{1}'.format(self.proxy_address, type_address)
        service = client.create_service(binding_name, address)
        return service

    def send_invoice(self):
        msg_header, msg_invoice = self.get_msg()
        try:
            if self.invoice.type.startswith('out_'):
                res = self.emitted_service.SuministroLRFacturasEmitidas(
                    msg_header, msg_invoice)
            elif self.invoice.type.startswith('in_'):
                res = self.received_service.SuministroLRFacturasRecibidas(
                    msg_header, msg_invoice)
            self.result = {
                            'sii_sent': res['EstadoEnvio'] == 'Correcto',
                            'sii_return': res
                          }
            return self.result
            # self.result['sii_sent'] = res['EstadoEnvio'] == 'Correcto'
            # self.result['sii_return'] = res
        except Exception as fault:
            self.result = fault
            raise fault

    # def list_invoice(self, invoice):
    #     msg_header, msg_invoice = self.get_msg(invoice)
    #     try:
    #         if invoice.type == 'in_invoice':
    #             res = self.received_service.ConsultaLRFacturasRecibidas(
    #                 msg_header, msg_invoice)
    #             if res['EstadoEnvio'] == 'Correcto':
    #                 self.result['sii_sent'] = True
    #             self.result['sii_return'] = res
    #     except Exception as fault:
    #         self.result['sii_return'] = fault

    def get_msg(self):
        dict_from_marsh = SII.generate_object(self.invoice)
        res_header = res_invoices = None
        if self.invoice.type.startswith('out_'):
            res_header = dict_from_marsh['SuministroLRFacturasEmitidas'][
                'Cabecera']
            res_invoices = dict_from_marsh['SuministroLRFacturasEmitidas'][
                'RegistroLRFacturasEmitidas']
        elif self.invoice.type.startswith('in_'):
            res_header = dict_from_marsh['SuministroLRFacturasRecibidas'][
                'Cabecera']
            res_invoices = dict_from_marsh['SuministroLRFacturasRecibidas'][
                'RegistroLRFacturasRecibidas']

        return res_header, res_invoices

    wsdl_files = {
        'emitted_invoice': 'http://www.agenciatributaria.es/static_files/AEAT/Contenidos_Comunes/La_Agencia_Tributaria/Modelos_y_formularios/Suministro_inmediato_informacion/FicherosSuministros/V_07/SuministroFactEmitidas.wsdl',
        'received_invoice': 'http://www.agenciatributaria.es/static_files/AEAT/Contenidos_Comunes/La_Agencia_Tributaria/Modelos_y_formularios/Suministro_inmediato_informacion/FicherosSuministros/V_07/SuministroFactRecibidas.wsdl',
    }