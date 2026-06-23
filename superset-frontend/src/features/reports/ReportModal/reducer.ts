/**
 * Licensed to the Apache Software Foundation (ASF) under one
 * or more contributor license agreements.  See the NOTICE file
 * distributed with this work for additional information
 * regarding copyright ownership.  The ASF licenses this file
 * to you under the Apache License, Version 2.0 (the
 * "License"); you may not use this file except in compliance
 * with the License.  You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing,
 * software distributed under the License is distributed on an
 * "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
 * KIND, either express or implied.  See the License for the
 * specific language governing permissions and limitations
 * under the License.
 */
/* eslint-disable camelcase */
import { omit } from 'lodash';
import {
  SET_REPORT,
  ADD_REPORT,
  SUBSCRIBE_REPORT,
  EDIT_REPORT,
  DELETE_REPORT,
  ReportAction,
  SetReportAction,
  AddReportAction,
  SubscribeReportAction,
  EditReportAction,
  DeleteReportAction,
  DeletableReport,
} from './actions';
import { ReportObject, ReportCreationMethod } from 'src/features/reports/types';

export interface ReportsState {
  dashboards?: Record<number, ReportObject>;
  charts?: Record<number, ReportObject>;
  alerts_reports?: Record<number, ReportObject>;
}

type ReportStateKeySource = Pick<
  ReportObject | DeletableReport,
  'id' | 'dashboard' | 'chart' | 'creation_method'
>;

const getReportStateKey = (report: ReportStateKeySource): number | undefined => {
  if (report.creation_method === 'alerts_reports') {
    return report.id;
  }

  return report.dashboard ?? report.chart;
};

const upsertReport = (
  state: ReportsState,
  report: ReportObject,
): ReportsState => {
  const creationMethod = report.creation_method as ReportCreationMethod;
  const key = getReportStateKey(report);

  if (key === undefined) {
    return state;
  }

  return {
    ...state,
    [creationMethod]: {
      ...state[creationMethod],
      [key]: report,
    },
  };
};

const removeReport = (
  state: ReportsState,
  report: ReportStateKeySource,
): ReportsState => {
  const creationMethod = report.creation_method as ReportCreationMethod;
  const key = getReportStateKey(report);

  if (key === undefined) {
    return state;
  }

  const methodState = state[creationMethod];
  return {
    ...state,
    [creationMethod]: methodState ? omit(methodState, key) : undefined,
  };
};

export default function reportsReducer(
  state: ReportsState = {},
  action: ReportAction,
): ReportsState {
  switch (action.type) {
    case SET_REPORT: {
      const { report, resourceId, creationMethod, filterField } =
        action as SetReportAction;
      const propertyName =
        filterField === 'dashboard_id' ? 'dashboard' : 'chart';
      const reportObject = report.result?.find(
        (reportResult: ReportObject) =>
          reportResult[propertyName] === resourceId,
      );

      if (reportObject) {
        return {
          ...state,
          [creationMethod]: {
            ...state[creationMethod],
            [resourceId]: reportObject,
          },
        };
      }

      const existingMethodState = state[creationMethod];
      if (existingMethodState?.[resourceId]) {
        return {
          ...state,
          [creationMethod]: omit(existingMethodState, resourceId),
        };
      }

      return { ...state };
    }

    case ADD_REPORT: {
      const { result, id } = (action as AddReportAction).json;
      return upsertReport(state, { ...result, id } as ReportObject);
    }

    case SUBSCRIBE_REPORT: {
      const { result, id } = (action as SubscribeReportAction).json;
      return upsertReport(state, { ...result, id } as ReportObject);
    }

    case EDIT_REPORT: {
      const { result, id } = (action as EditReportAction).json;
      return upsertReport(state, { ...result, id } as ReportObject);
    }

    case DELETE_REPORT:
      return removeReport(state, (action as DeleteReportAction).report);

    default:
      return state;
  }
}
