#
# Copyright: https://github.com/mlcommons/ck/blob/master/cm-mlops/COPYRIGHT.md
# License: https://github.com/mlcommons/ck/blob/master/cm-mlops/LICENSE.md
#
# White paper: https://arxiv.org/abs/2406.16791
# History: https://github.com/mlcommons/ck/blob/master/HISTORY.CM.md
# Original repository: https://github.com/mlcommons/ck/tree/master/cm-mlops
#
# CK and CM project contributors: https://github.com/mlcommons/ck/blob/master/CONTRIBUTING.md
#

from cmind import utils
import os
import json
import shutil
import subprocess


def preprocess(i):

    os_info = i['os_info']
    env = i['env']
    state = i['state']
    script_path = i['run_script_input']['path']

    if env.get('CM_MLPERF_SKIP_RUN', '') == "yes":
        return {'return': 0}

    if env.get('CM_RUN_DOCKER_CONTAINER', '') == "yes":
        return {'return': 0}

    if env.get('CM_MLPERF_POWER', '') == "yes":
        power = "yes"
    else:
        power = "no"

    rerun = True if env.get("CM_RERUN", "") != '' else False

    if 'CM_MLPERF_LOADGEN_SCENARIO' not in env:
        env['CM_MLPERF_LOADGEN_SCENARIO'] = "Offline"

    if 'CM_MLPERF_LOADGEN_MODE' not in env:
        env['CM_MLPERF_LOADGEN_MODE'] = "accuracy"

    if 'CM_MODEL' not in env:
        return {
            'return': 1, 'error': "Please select a variation specifying the model to run"}

    # if env['CM_MODEL'] == "resnet50":
    #    cmd = "cp " + os.path.join(env['CM_DATASET_AUX_PATH'], "val.txt") + " " + os.path.join(env['CM_DATASET_PATH'],
    #    "val_map.txt")
    #    ret = os.system(cmd)

    env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] = " " + \
        env.get('CM_MLPERF_LOADGEN_EXTRA_OPTIONS', '') + " "

    if 'CM_MLPERF_LOADGEN_QPS' not in env:
        env['CM_MLPERF_LOADGEN_QPS_OPT'] = ""
    else:
        env['CM_MLPERF_LOADGEN_QPS_OPT'] = " --qps " + \
            env['CM_MLPERF_LOADGEN_QPS']

    env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += env['CM_MLPERF_LOADGEN_QPS_OPT']

    if 'CM_NUM_THREADS' not in env:
        if 'CM_MINIMIZE_THREADS' in env:
            env['CM_NUM_THREADS'] = str(int(env['CM_HOST_CPU_TOTAL_CORES']) //
                                        (int(env.get('CM_HOST_CPU_SOCKETS', '1')) * int(env.get('CM_HOST_CPU_TOTAL_CORES', '1'))))
        else:
            env['CM_NUM_THREADS'] = env.get('CM_HOST_CPU_TOTAL_CORES', '1')

    if env.get('CM_MLPERF_LOADGEN_MAX_BATCHSIZE', '') != '' and str(env.get(
            'CM_MLPERF_MODEL_SKIP_BATCHING', False)).lower() not in ["true", "1", "yes"]:
        env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += " --max-batchsize " + \
            str(env['CM_MLPERF_LOADGEN_MAX_BATCHSIZE'])

    if env.get('CM_MLPERF_LOADGEN_BATCH_SIZE', '') != '':
        env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += " --batch-size " + \
            str(env['CM_MLPERF_LOADGEN_BATCH_SIZE'])

    if env.get('CM_MLPERF_LOADGEN_QUERY_COUNT', '') != '' and not env.get('CM_TMP_IGNORE_MLPERF_QUERY_COUNT', False) and (
            env['CM_MLPERF_LOADGEN_MODE'] == 'accuracy' or 'gptj' in env['CM_MODEL'] or 'llama2' in env['CM_MODEL'] or 'mixtral' in env['CM_MODEL'] or 'llama3' in env['CM_MODEL']) and env.get('CM_MLPERF_RUN_STYLE', '') != "valid":
        env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += " --count " + \
            env['CM_MLPERF_LOADGEN_QUERY_COUNT']

    print("Using MLCommons Inference source from '" +
          env['CM_MLPERF_INFERENCE_SOURCE'] + "'")

    if 'CM_MLPERF_CONF' not in env:
        env['CM_MLPERF_CONF'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'], "mlperf.conf")

    x = "" if os_info['platform'] == 'windows' else "'"

    inference_src_version = env.get('CM_MLPERF_INFERENCE_SOURCE_VERSION', '')
    version_tuple = None
    if inference_src_version:
        version_tuple = tuple(map(int, inference_src_version.split('.')))

    if version_tuple and version_tuple >= (4, 1, 1):
        pass  # mlperf_conf is automatically loaded by the loadgen
    else:
        if "llama2-70b" in env['CM_MODEL'] or "mixtral-8x7b" in env["CM_MODEL"]:
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += " --mlperf-conf " + \
                x + env['CM_MLPERF_CONF'] + x
        else:
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] += " --mlperf_conf " + \
                x + env['CM_MLPERF_CONF'] + x

    if env.get('CM_NETWORK_LOADGEN', '') != "lon" and env.get(
            'CM_MLPERF_INFERENCE_API_SERVER', '') == '' and "llama2-70b" not in env['CM_MODEL']:
        env['MODEL_DIR'] = env.get('CM_ML_MODEL_PATH')
        if not env['MODEL_DIR']:
            env['MODEL_DIR'] = os.path.dirname(
                env.get(
                    'CM_MLPERF_CUSTOM_MODEL_PATH',
                    env.get(
                        'CM_ML_MODEL_FILE_WITH_PATH',
                        '')))

    RUN_CMD = ""
    state['RUN'] = {}

    scenario = env['CM_MLPERF_LOADGEN_SCENARIO']
    state['RUN'][scenario] = {}
    scenario_extra_options = ''

    NUM_THREADS = env['CM_NUM_THREADS']
    if int(
            NUM_THREADS) > 2 and env['CM_MLPERF_DEVICE'] == "gpu" and env['CM_MODEL'] != "rgat":
        NUM_THREADS = "2"  # Don't use more than 2 threads when run on GPU

    if env['CM_MODEL'] in ['resnet50', 'retinanet',
                           'stable-diffusion-xl', 'rgat']:
        scenario_extra_options += " --threads " + NUM_THREADS

    ml_model_name = env['CM_MODEL']
    if 'CM_MLPERF_USER_CONF' in env:
        user_conf_path = env['CM_MLPERF_USER_CONF']
        x = "" if os_info['platform'] == 'windows' else "'"
        if 'llama2-70b' in env['CM_MODEL'] or "mixtral-8x7b" in env["CM_MODEL"] or "llama3" in env["CM_MODEL"]:
            scenario_extra_options += " --user-conf " + x + user_conf_path + x
        else:
            scenario_extra_options += " --user_conf " + x + user_conf_path + x

    mode = env['CM_MLPERF_LOADGEN_MODE']
    mode_extra_options = ""

    if 'CM_DATASET_PREPROCESSED_PATH' in env and env['CM_MODEL'] in [
            'resnet50', 'retinanet']:
        # dataset_options = " --use_preprocessed_dataset --preprocessed_dir "+env['CM_DATASET_PREPROCESSED_PATH']
        if env.get('CM_MLPERF_LAST_RELEASE') not in ["v2.0", "v2.1"]:
            dataset_options = " --use_preprocessed_dataset --cache_dir " + \
                env['CM_DATASET_PREPROCESSED_PATH']
        else:
            dataset_options = ""
        if env['CM_MODEL'] == "retinanet":
            dataset_options += " --dataset-list " + \
                env['CM_DATASET_ANNOTATIONS_FILE_PATH']
        elif env['CM_MODEL'] == "resnet50":
            dataset_options += " --dataset-list " + \
                os.path.join(env['CM_DATASET_AUX_PATH'], "val.txt")
        env['DATA_DIR'] = env.get('CM_DATASET_PREPROCESSED_PATH')
    else:
        if 'CM_DATASET_PREPROCESSED_PATH' in env:
            env['DATA_DIR'] = env.get('CM_DATASET_PREPROCESSED_PATH')
        else:
            env['DATA_DIR'] = env.get('CM_DATASET_PATH')

        if "dlrm" in env['CM_MODEL']:
            env['DATA_DIR'] = env['CM_CRITEO_PREPROCESSED_PATH']

        dataset_options = ''

    if env.get('CM_MLPERF_EXTRA_DATASET_ARGS', '') != '':
        dataset_options += " " + env['CM_MLPERF_EXTRA_DATASET_ARGS']

    if mode == "accuracy":
        mode_extra_options += " --accuracy"

    elif mode == "performance":
        pass

    elif mode == "compliance":

        audit_full_path = env['CM_MLPERF_INFERENCE_AUDIT_PATH']
        mode_extra_options = " --audit '" + audit_full_path + "'"

    if env.get('CM_MLPERF_OUTPUT_DIR', '') == '':
        env['CM_MLPERF_OUTPUT_DIR'] = os.getcwd()

    mlperf_implementation = env.get('CM_MLPERF_IMPLEMENTATION', 'reference')
    cmd, run_dir = get_run_cmd(os_info, env, scenario_extra_options,
                               mode_extra_options, dataset_options, mlperf_implementation)

    if env.get('CM_NETWORK_LOADGEN', '') == "lon":

        run_cmd = i['state']['mlperf_inference_run_cmd']
        env['CM_SSH_RUN_COMMANDS'] = []
        env['CM_SSH_RUN_COMMANDS'].append(
            run_cmd.replace(
                "--network=lon",
                "--network=sut") + " &")

    env['CM_MLPERF_RUN_CMD'] = cmd
    env['CM_RUN_DIR'] = run_dir
    env['CM_RUN_CMD'] = cmd
    env['CK_PROGRAM_TMP_DIR'] = env.get('CM_ML_MODEL_PATH')  # for tvm

    if env.get('CM_HOST_PLATFORM_FLAVOR', '') == "arm64":
        env['CM_HOST_PLATFORM_FLAVOR'] = "aarch64"

    return {'return': 0}


def get_run_cmd(os_info, env, scenario_extra_options,
                mode_extra_options, dataset_options, implementation="reference"):
    if implementation == "reference":
        return get_run_cmd_reference(
            os_info, env, scenario_extra_options, mode_extra_options, dataset_options)
    if implementation == "nvidia":
        return get_run_cmd_nvidia(
            os_info, env, scenario_extra_options, mode_extra_options, dataset_options)
    return "", os.getcwd()


def get_run_cmd_reference(
        os_info, env, scenario_extra_options, mode_extra_options, dataset_options):

    if env['CM_MODEL'] in ["gptj-99", "gptj-99.9"]:

        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'], "language", "gpt-j")
        if env.get('CM_NETWORK_LOADGEN', '') != "lon":
            cmd = env['CM_PYTHON_BIN_WITH_PATH'] +  \
                " main.py --model-path=" + env['CM_ML_MODEL_FILE_WITH_PATH'] + ' --dataset-path=' + env['CM_DATASET_EVAL_PATH'] + " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + " " + env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
                ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION'] + \
                scenario_extra_options + mode_extra_options + dataset_options
        else:
            cmd = env['CM_PYTHON_BIN_WITH_PATH'] +  \
                " main.py" + ' --dataset-path=' + env['CM_DATASET_EVAL_PATH'] + " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + " " + env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
                ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION'] + \
                scenario_extra_options + mode_extra_options + dataset_options
        cmd = cmd.replace("--count", "--max_examples")
        if env['CM_MLPERF_DEVICE'] == "gpu":
            gpu_options = " --gpu"
            env['CUDA_VISIBLE_DEVICES'] = "0"
        else:
            gpu_options = ""
        cmd = cmd + gpu_options
        env['LOG_PATH'] = env['CM_MLPERF_OUTPUT_DIR']

    if env['CM_MODEL'] in ["resnet50", "retinanet"]:

        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'],
            "vision",
            "classification_and_detection")
        env['OUTPUT_DIR'] = env['CM_MLPERF_OUTPUT_DIR']
        if env.get('CM_MLPERF_VISION_DATASET_OPTION', '') == '' and env.get(
                'CM_MLPERF_DEVICE') != "tpu":
            if os_info['platform'] == 'windows':
                cmd = "python python/main.py --profile " + env['CM_MODEL'] + "-" + env['CM_MLPERF_BACKEND'] + \
                    " --model=" + env['CM_ML_MODEL_FILE_WITH_PATH'] + ' --dataset-path=' + env['CM_DATASET_PREPROCESSED_PATH'] + \
                    " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + " " + \
                    " --output " + env['OUTPUT_DIR'] + " " + \
                    env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
                    scenario_extra_options + mode_extra_options + dataset_options
            else:
                cmd = "./run_local.sh " + env['CM_MLPERF_BACKEND'] + ' ' + \
                    env['CM_MODEL'] + ' ' + env['CM_MLPERF_DEVICE'] + " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + " " + env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
                    scenario_extra_options + mode_extra_options + dataset_options
            return cmd, env['RUN_DIR']

        if env['CM_MLPERF_BACKEND'] == "ncnn":
            env['MODEL_FILE'] = os.path.join(
                os.path.dirname(
                    env.get('CM_ML_MODEL_FILE_WITH_PATH')),
                "resnet50_v1")
        else:
            env['MODEL_FILE'] = env.get(
                'CM_MLPERF_CUSTOM_MODEL_PATH',
                env.get('CM_ML_MODEL_FILE_WITH_PATH'))
        if not env['MODEL_FILE']:
            return {'return': 1, 'error': 'No valid model file found!'}

        env['LOG_PATH'] = env['CM_MLPERF_OUTPUT_DIR']

        extra_options = " --output " + env['CM_MLPERF_OUTPUT_DIR'] + " --model-name resnet50  --dataset " + env['CM_MLPERF_VISION_DATASET_OPTION'] + ' --max-batchsize ' + env.get('CM_MLPERF_LOADGEN_MAX_BATCHSIZE', '1') + \
            " --dataset-path " + env['CM_DATASET_PREPROCESSED_PATH'] + " --model " + env['MODEL_FILE'] + \
            " --preprocessed_dir " + env['CM_DATASET_PREPROCESSED_PATH']

        if env.get('CM_MLPERF_DEVICE') == "tpu":
            cmd = "cd '" + os.path.join(env['RUN_DIR'], "python") + "' && " + env.get('CM_SUDO', "") + " " + env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " +\
                "--backend " + env['CM_MLPERF_BACKEND'] + " --scenario=" + env['CM_MLPERF_LOADGEN_SCENARIO'] + " --device tpu " + \
                env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + scenario_extra_options + \
                mode_extra_options + dataset_options + extra_options
        else:
            cmd = "cd '" + os.path.join(env['RUN_DIR'], "python") + "' && " + env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " +\
                "--backend " + env['CM_MLPERF_BACKEND'] + " --scenario=" + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
                env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + scenario_extra_options + \
                mode_extra_options + dataset_options + extra_options
        env['SKIP_VERIFY_ACCURACY'] = True

    elif "bert" in env['CM_MODEL']:

        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'], "language", "bert")
        env['MODEL_FILE'] = env.get(
            'CM_MLPERF_CUSTOM_MODEL_PATH',
            env.get('CM_ML_MODEL_FILE_WITH_PATH'))
        if not env['MODEL_FILE']:
            return {'return': 1, 'error': 'No valid model file found!'}
        if env.get('CM_MLPERF_QUANTIZATION') in ["on", True, "1", "True"]:
            quantization_options = " --quantized"
        else:
            quantization_options = ""
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " run.py --backend=" + env['CM_MLPERF_BACKEND'] + " --scenario=" + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + scenario_extra_options + \
            mode_extra_options + dataset_options + quantization_options
        if env['CM_MLPERF_BACKEND'] == "deepsparse":
            cmd += " --batch_size=" + \
                env.get('CM_MLPERF_LOADGEN_MAX_BATCHSIZE', '1') + \
                " --model_path=" + env['MODEL_FILE']

        if env.get('CM_MLPERF_CUSTOM_MODEL_PATH', '') != '':
            env['CM_ML_MODEL_FILE_WITH_PATH'] = env['MODEL_FILE']

        cmd = cmd.replace("--count", "--max_examples")
        env['VOCAB_FILE'] = env['CM_ML_MODEL_BERT_VOCAB_FILE_WITH_PATH']
        env['DATASET_FILE'] = env['CM_DATASET_SQUAD_VAL_PATH']
        env['LOG_PATH'] = env['CM_MLPERF_OUTPUT_DIR']
        env['SKIP_VERIFY_ACCURACY'] = True

    elif "rnnt" in env['CM_MODEL']:

        env['RUN_DIR'] = env['CM_MLPERF_INFERENCE_RNNT_PATH']
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " run.py --backend " + env['CM_MLPERF_BACKEND'] + \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --manifest " + env['CM_DATASET_PREPROCESSED_JSON'] + \
            " --dataset_dir " + os.path.join(env['CM_DATASET_PREPROCESSED_PATH'], "..") + \
            " --pytorch_config_toml " + os.path.join("pytorch", "configs", "rnnt.toml") + \
            " --pytorch_checkpoint " + env['CM_ML_MODEL_FILE_WITH_PATH'] + \
            " --log_dir " + env['CM_MLPERF_OUTPUT_DIR'] + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            scenario_extra_options + mode_extra_options + dataset_options
        env['SKIP_VERIFY_ACCURACY'] = True

    elif "stable-diffusion-xl" in env['CM_MODEL']:
        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'], "text_to_image")
        if env.get('+PYTHONPATH', '') == '':
            env['+PYTHONPATH'] = []
        env['+PYTHONPATH'].append(
            os.path.join(
                env['CM_MLPERF_INFERENCE_SOURCE'],
                "text_to_image",
                "tools",
                "fid"))

        backend = env['CM_MLPERF_BACKEND']
        device = env['CM_MLPERF_DEVICE'] if env['CM_MLPERF_DEVICE'] not in [
            "gpu", "rocm"] else "cuda"
        max_batchsize = env.get('CM_MLPERF_LOADGEN_MAX_BATCHSIZE', '1')
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --profile " + 'stable-diffusion-xl-pytorch ' + \
            " --dataset " + 'coco-1024' +  \
            " --dataset-path " + env['CM_DATASET_PATH_ROOT'] + \
            ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION'].replace("bfloat", "bf").replace("float", "fp") + \
            " --device " + device + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            scenario_extra_options + mode_extra_options + \
            " --output " + env['CM_MLPERF_OUTPUT_DIR'] + \
            " --model-path " + env['CM_ML_MODEL_PATH']
        if "--max-batchsize" not in cmd:
            cmd += " --max-batchsize " + max_batchsize
        if env.get('CM_COCO2014_SAMPLE_ID_PATH', '') != '':
            cmd += " --ids-path " + env['CM_COCO2014_SAMPLE_ID_PATH']

    elif "llama2-70b" in env['CM_MODEL']:
        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'],
            "language",
            "llama2-70b")
        backend = env['CM_MLPERF_BACKEND']
        device = env['CM_MLPERF_DEVICE'] if env['CM_MLPERF_DEVICE'] != "gpu" else "cuda"

        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --dataset-path " + env['CM_DATASET_PREPROCESSED_PATH'] + \
            " --device " + device.replace("cuda", "cuda:0") + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            scenario_extra_options + mode_extra_options + \
            " --output-log-dir " + env['CM_MLPERF_OUTPUT_DIR'] + \
            ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION']

        if env.get('CM_MLPERF_INFERENCE_API_SERVER', '') != '':
            env['CM_VLLM_SERVER_MODEL_NAME'] = env.get(
                "CM_VLLM_SERVER_MODEL_NAME") or "NousResearch/Meta-Llama-3-8B-Instruct"
            # env['CM_MLPERF_INFERENCE_API_SERVER'] = "http://localhost:8000"
            cmd += f""" --api-server {env['CM_MLPERF_INFERENCE_API_SERVER']} \
                    --model-path {env['CM_VLLM_SERVER_MODEL_NAME']} \
                    --api-model-name {env['CM_VLLM_SERVER_MODEL_NAME']} --vllm """
        else:
            cmd += f" --model-path {env['LLAMA2_CHECKPOINT_PATH']}"

        if env.get('CM_MLPERF_INFERENCE_NUM_WORKERS', '') != '':
            cmd += f" --num-workers {env['CM_MLPERF_INFERENCE_NUM_WORKERS']}"

        cmd = cmd.replace("--count", "--total-sample-count")
        cmd = cmd.replace("--max-batchsize", "--batch-size")

    elif "mixtral-8x7b" in env['CM_MODEL']:
        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'],
            "language",
            "mixtral-8x7b")
        backend = env['CM_MLPERF_BACKEND']
        device = env['CM_MLPERF_DEVICE'] if env['CM_MLPERF_DEVICE'] != "gpu" else "cuda"
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --dataset-path " + env['CM_DATASET_MIXTRAL_PREPROCESSED_PATH'] + \
            " --device " + device.replace("cuda", "cuda:0") + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            scenario_extra_options + mode_extra_options + \
            " --output-log-dir " + env['CM_MLPERF_OUTPUT_DIR'] + \
            ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION'] + \
            " --model-path " + env['MIXTRAL_CHECKPOINT_PATH']
        cmd = cmd.replace("--count", "--total-sample-count")
        cmd = cmd.replace("--max-batchsize", "--batch-size")

    elif "3d-unet" in env['CM_MODEL']:

        env['RUN_DIR'] = env['CM_MLPERF_INFERENCE_3DUNET_PATH']
        backend = env['CM_MLPERF_BACKEND'] if env['CM_MLPERF_BACKEND'] != 'tf' else 'tensorflow'
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " run.py --backend=" + backend + " --scenario=" + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            " --model=" + env['CM_ML_MODEL_FILE_WITH_PATH'] + \
            " --preprocessed_data_dir=" + env['CM_DATASET_KITS19_PREPROCESSED_PATH'] + \
            scenario_extra_options + mode_extra_options + dataset_options

        env['LOG_PATH'] = env['CM_MLPERF_OUTPUT_DIR']
        env['SKIP_VERIFY_ACCURACY'] = True

    elif "dlrm" in env['CM_MODEL']:  # DLRM is in draft stage

        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_DLRM_V2_PATH'], "pytorch")
        if 'multihot-criteo-sample' in env['CM_ML_MODEL_DATASET_TYPE']:
            dataset = "multihot-criteo-sample"
        elif 'multihot-criteo' in env['CM_ML_MODEL_DATASET_TYPE']:
            dataset = "multihot-criteo"

        env['MODEL_DIR'] = os.path.join(env['MODEL_DIR'], "model_weights")

        if env.get('CM_MLPERF_BIN_LOADER', '') == 'yes':
            mlperf_bin_loader_string = " --mlperf-bin-loader"
        else:
            mlperf_bin_loader_string = ""
        if env.get('CM_ML_MODEL_DEBUG', '') == 'yes':
            config = " --max-ind-range=10000000 --data-sub-sample-rate=0.875 "
        else:
            config = "  --max-ind-range=40000000 "

        if env['CM_MLPERF_DEVICE'] == "gpu":
            gpu_options = ""
            env['CUDA_VISIBLE_DEVICES'] = "0"
        else:
            gpu_options = ""
            env['WORLD_SIZE'] = "1"

        if env['CM_MLPERF_LOADGEN_MODE'] == "accuracy" and env['CM_MLPERF_LOADGEN_SCENARIO'] == "Offline":
            mode_extra_options += " --samples-per-query-offline=1"

        cmd = " ./run_local.sh " + env['CM_MLPERF_BACKEND'] + \
            ' dlrm ' + dataset + ' ' + env['CM_MLPERF_DEVICE'] + " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + " " + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            config + mlperf_bin_loader_string + \
            ' --samples-to-aggregate-quantile-file=./tools/dist_quantile.txt ' + \
            scenario_extra_options + mode_extra_options + dataset_options + gpu_options
        cmd = cmd.replace("--count", "--count-queries")
        env['OUTPUT_DIR'] = env['CM_MLPERF_OUTPUT_DIR']

    elif "rgat" in env['CM_MODEL']:
        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'],
            "graph",
            "R-GAT")
        backend = env['CM_MLPERF_BACKEND']

        dtype_rgat = env['CM_MLPERF_MODEL_PRECISION'].replace("float", "fp")

        if env.get('CM_MLPERF_SUBMISSION_GENERATION_STYLE', '') == "full":
            mode_extra_options += " --dataset igbh-dgl --profile rgat-dgl-full "
        else:
            mode_extra_options += " --dataset igbh-dgl-tiny --profile debug-dgl "

        device = env['CM_MLPERF_DEVICE'] if env['CM_MLPERF_DEVICE'] != "gpu" else "cuda"
        # have to add the condition for running in debug mode or real run mode
        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --dataset-path " + env['CM_DATASET_IGBH_PATH'] + \
            " --device " + device.replace("cuda", "gpu") + \
            env['CM_MLPERF_LOADGEN_EXTRA_OPTIONS'] + \
            scenario_extra_options + mode_extra_options + \
            " --output " + env['CM_MLPERF_OUTPUT_DIR'] + \
            ' --dtype ' + dtype_rgat + \
            " --model-path " + env['RGAT_CHECKPOINT_PATH']

        if env.get('CM_ACTIVATE_RGAT_IN_MEMORY', '') == "yes":
            cmd += " --in-memory "

    elif "llama3" in env['CM_MODEL']:
        env['RUN_DIR'] = os.path.join(
            env['CM_MLPERF_INFERENCE_SOURCE'],
            "language",
            "llama3.1-405b")

        if int(env.get('CM_MLPERF_INFERENCE_TP_SIZE', '')) > 1:
            env['VLLM_WORKER_MULTIPROC_METHOD'] = "spawn"

        cmd = env['CM_PYTHON_BIN_WITH_PATH'] + " main.py " \
            " --scenario " + env['CM_MLPERF_LOADGEN_SCENARIO'] + \
            " --dataset-path " + env['CM_DATASET_LLAMA3_PATH'] + \
            " --output-log-dir " + env['CM_MLPERF_OUTPUT_DIR'] + \
            ' --dtype ' + env['CM_MLPERF_MODEL_PRECISION'] + \
            " --model-path " + env['CM_ML_MODEL_LLAMA3_CHECKPOINT_PATH'] + \
            " --tensor-parallel-size " + env['CM_MLPERF_INFERENCE_TP_SIZE'] + \
            " --vllm "

        if env.get('CM_MLPERF_INFERENCE_NUM_WORKERS', '') != '':
            cmd += f" --num-workers {env['CM_MLPERF_INFERENCE_NUM_WORKERS']}"

        cmd = cmd.replace("--count", "--total-sample-count")
        cmd = cmd.replace("--max-batchsize", "--batch-size")

    if env.get('CM_NETWORK_LOADGEN', '') in ["lon", "sut"]:
        cmd = cmd + " " + "--network " + env['CM_NETWORK_LOADGEN']
        if env.get('CM_NETWORK_LOADGEN_SUT_SERVERS', []):
            sut_servers = env['CM_NETWORK_LOADGEN_SUT_SERVERS']
            cmd += " --sut_server '" + "','".join(sut_servers) + "' "

    return cmd, env['RUN_DIR']


def postprocess(i):

    env = i['env']
    state = i['state']

    inp = i['input']

    return {'return': 0}
