import urllib2
import os
import xml.etree.ElementTree as etree
from .objects import Ticket

def authenticated(func):
    def add_auth(self, *args, **kwargs):
        if self.session_id:
            kwargs['SessionID'] = self.session_id
        elif self.login and self.password:
            kwargs['UserLogin'] = self.login
            kwargs['Password'] = self.password
        else:
            raise ValueError(
                'You should define either login/password or session_id')

        return func(self,*args, **kwargs)
    return add_auth


class NoCredentialsException(Exception):
    def __str__(self):
        return 'Register credentials first with register_credentials() method'


SOAP_ENVELOPPE = """
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"
                  xmlns="http://www.otrs.org/TicketConnector/">
  <soapenv:Header/>
  <soapenv:Body>{}</soapenv:Body>
</soapenv:Envelope>
"""

class OTRSError(Exception):
    def __init__(self, fd):
        self.code = fd.getcode()
        self.msg = fd.read()

    def __str__(self):
        return '{} : {}'.format(self.code, self.msg)


class GenericTicketConnector(object):
    """ Client for the GenericTicketConnector SOAP API

    see http://otrs.github.io/doc/manual/admin/3.3/en/html/genericinterface.html
    """
    requests = {
        'TicketCreate'  : None,
        'TicketUpdate'  : [],
        'TicketGet'     : None,
        'TicketSearch'  : None,
        'SessionCreate' : [('UserLogin', 'Password'),
                               ('CustomerUserLogin', 'Password')]
    }

    def __init__(self, server, webservice_name='GenericTicketConnector'):
        """ @param server : the http(s) URL of the root installation of OTRS
                            (e.g: https://tickets.example.net)

            @param webservice_name : the name of the installed webservice
                   (choosen by the otrs admin).
        """

        self.endpoint = os.path.join(
            server,
            'otrs/nph-genericinterface.pl/Webservice',
            webservice_name)
        self.login = None
        self.password = None
        self.session_id = None

    def register_credentials(self, login, password):
        self.login = login
        self.password = password

    def req(self, reqname, with_auth=False, *args, **kwargs):
        if not self.login or not self.password:
            raise NoCredentialsException()

        xml_req_root = etree.Element(reqname)

        for k,v in kwargs.items():
            e = etree.Element(k)
            e.text = str(v)
            xml_req_root.append(e)

        request = urllib2.Request(
            self.endpoint, self._pack_req(xml_req_root),
            {'Content-Type': 'text/xml;charset=utf-8'}
        )
        fd = urllib2.urlopen(request)
        if fd.getcode() != 200:
            raise OTRSError(fd)
        else:
            try:
                s = fd.read()
                return etree.fromstring(s)
            except etree.ParseError:
                print 'error parsing:'
                print s
                raise

    @staticmethod
    def _unpack_resp_several(element):
        return element.getchildren()[0].getchildren()[0].getchildren()

    @staticmethod
    def _unpack_resp_one(element):
        return element.getchildren()[0].getchildren()[0].getchildren()[0]

    @staticmethod
    def _pack_req(element):
        return SOAP_ENVELOPPE.format(etree.tostring(element))

    def session_create(self, password, user_login=None,
                                       customer_user_login=None):
        if user_login:
            ret = self.req('SessionCreate',
                           UserLogin = user_login,
                           Password  = password)
        else:
            ret = self.req('SessionCreate',
                           CustomerUserLogin = customer_user_login,
                           Password          = password)
        signal = self._unpack_resp_one(ret)
        session_id = signal.text
        return session_id

    def user_session_register(self, user, password):
        self.session_id = self.session_create(
            password=password,
            user_login=user)

    def customer_user_session_register(self, user, password):
        self.session_id = self.session_create(
            password=password,
            customer_user_login=user)

    @authenticated
    def ticket_get(self, ticket_id, *args, **kwargs):
        """ Get a ticket by id ; beware, TicketID != TicketNumber
        """
        params = {'TicketID' : str(ticket_id)}
        params.update(kwargs)
        ret = self.req('TicketGet', **params)
        return Ticket.from_xml(self._unpack_resp_one(ret))

    @authenticated
    def ticket_search(self, **kwargs):
        """
        @returns a list of matching TicketID
        """
        ret = self.req('TicketSearch', **kwargs)
        return [int(i.text) for i in self._unpack_resp_several(ret)]


    def ticket_create(self, ticket, article, **kwargs):
        """
        @param ticket a Ticket
        @param article an Article
        """
        ticket_requirements = (
            ('StateID', 'State'),
            ('PriorityID', 'Priority'),
            ('QueueID', 'Queue'),
        )
        article_requirements = ('Subject', 'Body', 'Charset', 'MimeType')
        ticket.check_fields(ticket_requirements)
        article.check_fields(article_requirements)