import kubernetes
import sys
from six import iteritems
import subprocess
import os
import yaml
from contextlib import suppress
import urllib3.exceptions
import socket
import json


class CustomObjectsApiWithUpdate(kubernetes.client.CustomObjectsApi):
    def update_namespaced_custom_object(self, group, version, namespace, plural, name, body, **kwargs):
        kwargs['_return_http_data_only'] = True
        if kwargs.get('callback'):
            return self.update_namespaced_custom_object_with_http_info(group, version, namespace, plural, name, body, **kwargs)
        else:
            (data) = self.update_namespaced_custom_object_with_http_info(group, version, namespace, plural, name, body, **kwargs)
            return data

    def update_namespaced_custom_object_with_http_info(self, group, version, namespace, plural, name, body, **kwargs):
        all_params = ['group', 'version', 'namespace', 'plural', 'name', 'body']
        all_params.append('callback')
        all_params.append('_return_http_data_only')
        all_params.append('_preload_content')
        all_params.append('_request_timeout')

        params = locals()
        for key, val in iteritems(params['kwargs']):
            if key not in all_params:
                raise TypeError(
                    "Got an unexpected keyword argument '%s'"
                    " to method update_namespaced_custom_object" % key
                )
            params[key] = val
        del params['kwargs']
        # verify the required parameter 'group' is set
        if ('group' not in params) or (params['group'] is None):
            raise ValueError("Missing the required parameter `group` when calling `update_namespaced_custom_object`")
        # verify the required parameter 'version' is set
        if ('version' not in params) or (params['version'] is None):
            raise ValueError("Missing the required parameter `version` when calling `update_namespaced_custom_object`")
        # verify the required parameter 'namespace' is set
        if ('namespace' not in params) or (params['namespace'] is None):
            raise ValueError("Missing the required parameter `namespace` when calling `update_namespaced_custom_object`")
        # verify the required parameter 'plural' is set
        if ('plural' not in params) or (params['plural'] is None):
            raise ValueError("Missing the required parameter `plural` when calling `update_namespaced_custom_object`")
        # verify the required parameter 'name' is set
        if ('name' not in params) or (params['name'] is None):
            raise ValueError("Missing the required parameter `name` when calling `update_namespaced_custom_object`")
        # verify the required parameter 'body' is set
        if ('body' not in params) or (params['body'] is None):
            raise ValueError("Missing the required parameter `body` when calling `update_namespaced_custom_object`")

        collection_formats = {}

        resource_path = '/apis/{group}/{version}/namespaces/{namespace}/{plural}/{name}'.replace('{format}', 'json')
        path_params = {}
        if 'group' in params:
            path_params['group'] = params['group']
        if 'version' in params:
            path_params['version'] = params['version']
        if 'namespace' in params:
            path_params['namespace'] = params['namespace']
        if 'plural' in params:
            path_params['plural'] = params['plural']
        if 'name' in params:
            path_params['name'] = params['name']

        query_params = {}

        header_params = {}

        form_params = []
        local_var_files = {}

        body_params = None
        if 'body' in params:
            body_params = params['body']
        # HTTP header `Accept`
        header_params['Accept'] = self.api_client.\
            select_header_accept(['application/json'])

        # HTTP header `Content-Type`
        header_params['Content-Type'] = self.api_client.\
            select_header_content_type(['application/merge-patch+json', 'application/strategic-merge-patch+json'])

        # Authentication setting
        auth_settings = ['BearerToken']

        return self.api_client.call_api(resource_path, 'PATCH',
                                        path_params,
                                        query_params,
                                        header_params,
                                        body=body_params,
                                        post_params=form_params,
                                        files=local_var_files,
                                        response_type='object',
                                        auth_settings=auth_settings,
                                        callback=params.get('callback'),
                                        _return_http_data_only=params.get('_return_http_data_only'),
                                        _preload_content=params.get('_preload_content', True),
                                        _request_timeout=params.get('_request_timeout'),
                                        collection_formats=collection_formats)


def parse(o, prefix=""):
    def flatten(lis):
        new_lis = []
        for item in lis:
            if isinstance(item, list):
                new_lis.extend(flatten(item))
            else:
                new_lis.append(item)
        return new_lis

    try:
        return {
            "str": lambda: (prefix, o),
            "int": lambda: parse(str(o), prefix=prefix),
            "float": lambda: parse(str(o), prefix=prefix),
            "bool": lambda: parse(1 if o else 0, prefix=prefix),
            "NoneType": lambda: parse("", prefix=prefix),
            "list": lambda: flatten([parse(io, "{}{}{}".format(prefix, "_" if prefix else "", ik).upper()) for ik, io in enumerate(o)]),
            "dict": lambda: flatten([parse(io, "{}{}{}".format(prefix, "_" if prefix else "", ik).upper()) for ik, io in o.items()]),
        }[type(o).__name__]()
    except KeyError:
        raise


def wait_events(custom_objects_api_instance, fqdn, version, resource, apply_fn, delete_fn):
    w = kubernetes.watch.Watch()
    while True:
        with suppress(urllib3.exceptions.ReadTimeoutError, socket.timeout):
            for event in w.stream(custom_objects_api_instance.list_cluster_custom_object, fqdn, version, resource, _request_timeout=60):
                patch_object = {}
                object = event['object']
                namespace = object['metadata']['namespace']
                name = object['metadata']['name']
                object['metadata'].setdefault('finalizers', [])
                event_type = event['type']
                if event_type in ["ADDED", "MODIFIED"]:
                    if object['metadata'].get('deletionTimestamp', None) is not None:
                        if "Side8OperatorDelete" in object['metadata']['finalizers']:
                            patch_object['status'] = delete_fn(event['object'])
                            if not patch_object['status']:
                                patch_object['metadata'] = {'finalizers': list(filter(lambda f: f != "Side8OperatorDelete", object['metadata']['finalizers']))}
                        else:
                            try:
                                custom_objects_api_instance.delete_namespaced_custom_object(
                                        fqdn, version, namespace, resource,
                                        name, body=kubernetes.client.V1DeleteOptions())
                            except kubernetes.client.rest.ApiException as e:
                                if e.status != 404:
                                    # We're likely seeing an event for a resource that's already been deleted, ignore
                                    raise
                            except subprocess.CalledProcessError as e:
                                # TODO log k8s error event
                                print("delete exited with {}".format(e.returncode))
                                continue
                            continue
                    else:
                        if "Side8OperatorDelete" in object['metadata']['finalizers']:
                            try:
                                patch_object['status'] = apply_fn(event['object'])
                            except subprocess.CalledProcessError as e:
                                # TODO log k8s error event
                                print("apply exited with {}".format(e.returncode))
                                continue
                        else:
                            patch_object.setdefault('metadata', {})
                            patch_object['metadata'].setdefault('finalizers', [])
                            patch_object['metadata']['finalizers'].append("Side8OperatorDelete")

                    custom_objects_api_instance.update_namespaced_custom_object(
                            fqdn, version, namespace, resource, name,
                            patch_object)


def main():

    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument('--fqdn', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--resource', required=True)
    parser.add_argument('--apply', default="./apply")
    parser.add_argument('--delete', default="./delete")

    args = parser.parse_args()

    try:
        kubernetes.config.load_incluster_config()
        print("configured in cluster with service account")
    except Exception:
        try:
            kubernetes.config.load_kube_config()
            print("configured via kubeconfig file")
        except Exception:
            print("No Kubernetes configuration found")
            sys.exit(1)

    custom_objects_api_instance = CustomObjectsApiWithUpdate()

    fqdn = args.fqdn
    version = args.version
    resource = args.resource

    def apply_fn(event_object):
        print("running apply")
        subprocess_env = dict([("_DOLLAR", "$")] + parse(event_object, prefix="K8S") + [("K8S", json.dumps(event_object))])
        process = subprocess.Popen(
            [args.apply],
            env=dict(list(os.environ.items()) + list(subprocess_env.items())),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1)
        out, err = process.communicate()
        print("out: {}".format(out))
        print("error:")
        print(err.decode('utf-8'))
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args.apply)
        status = yaml.load(out)
        return status

    def delete_fn(event_object):
        print("running delete")
        subprocess_env = dict([("_DOLLAR", "$")] + parse(event_object, prefix="K8S") + [("K8S", json.dumps(event_object))])
        process = subprocess.Popen(
                [args.delete],
                env=dict(list(os.environ.items()) + list(subprocess_env.items())),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                bufsize=1)
        out, err = process.communicate()

        print("out: {}".format(out))
        print("error:")
        print(err.decode('utf-8'))
        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, args.delete)
        status = yaml.load(out)
        return status

    wait_events(custom_objects_api_instance, fqdn, version, resource, apply_fn, delete_fn)


if __name__ == '__main__':
    main()
